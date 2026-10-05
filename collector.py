import argparse
import socket
import time
from datetime import datetime, timezone

import psutil

from database import get_connection, initialize_database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def address_parts(address):
    if not address:
        return None, None

    try:
        return address.ip, address.port
    except AttributeError:
        try:
            return address[0], address[1]
        except (IndexError, TypeError):
            return None, None


def protocol_name(connection) -> str:
    if connection.type == socket.SOCK_STREAM:
        return "TCP"

    if connection.type == socket.SOCK_DGRAM:
        return "UDP"

    return str(connection.type)


def get_process_name(pid) -> str | None:
    if pid is None:
        return None

    try:
        return psutil.Process(pid).name()
    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        psutil.ZombieProcess
    ):
        return None


def collect_traffic(previous_counters, elapsed_seconds):
    current_counters = psutil.net_io_counters(pernic=True)
    timestamp = utc_now()
    rows = []

    for interface, current in current_counters.items():
        previous = previous_counters.get(interface)

        if previous is None:
            upload_rate = 0.0
            download_rate = 0.0
        else:
            sent_difference = max(
                0,
                current.bytes_sent - previous.bytes_sent
            )

            received_difference = max(
                0,
                current.bytes_recv - previous.bytes_recv
            )

            upload_rate = sent_difference / elapsed_seconds
            download_rate = received_difference / elapsed_seconds

        rows.append(
            (
                timestamp,
                interface,
                current.bytes_sent,
                current.bytes_recv,
                upload_rate,
                download_rate,
                current.packets_sent,
                current.packets_recv,
            )
        )

    return current_counters, rows


def collect_connections():
    timestamp = utc_now()
    rows = []

    try:
        connections = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        print(
            "Brak uprawnień do odczytu połączeń. "
            "Uruchom collector przez sudo."
        )
        return rows

    process_cache = {}

    for connection in connections:
        local_ip, local_port = address_parts(connection.laddr)
        remote_ip, remote_port = address_parts(connection.raddr)

        pid = connection.pid

        if pid not in process_cache:
            process_cache[pid] = get_process_name(pid)

        rows.append(
            (
                timestamp,
                protocol_name(connection),
                local_ip,
                local_port,
                remote_ip,
                remote_port,
                connection.status,
                pid,
                process_cache[pid],
            )
        )

    return rows


def save_samples(traffic_rows, connection_rows):
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO traffic_samples (
                timestamp,
                interface,
                bytes_sent_total,
                bytes_recv_total,
                upload_bytes_per_sec,
                download_bytes_per_sec,
                packets_sent_total,
                packets_recv_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            traffic_rows,
        )

        connection.executemany(
            """
            INSERT INTO connection_samples (
                timestamp,
                protocol,
                local_ip,
                local_port,
                remote_ip,
                remote_port,
                status,
                pid,
                process_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            connection_rows,
        )

        connection.commit()


def delete_old_samples(retention_days: int):
    modifier = f"-{retention_days} days"

    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM traffic_samples
            WHERE datetime(timestamp) < datetime('now', ?)
            """,
            (modifier,),
        )

        connection.execute(
            """
            DELETE FROM connection_samples
            WHERE datetime(timestamp) < datetime('now', ?)
            """,
            (modifier,),
        )

        connection.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Lokalny monitor ruchu sieciowego"
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Interwał próbkowania w sekundach",
    )

    parser.add_argument(
        "--connections-every",
        type=int,
        default=5,
        help="Zapis połączeń co N cykli",
    )

    parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
        help="Liczba dni przechowywania historii",
    )

    args = parser.parse_args()

    if args.interval <= 0:
        raise ValueError("--interval musi być większe od zera")

    if args.connections_every <= 0:
        raise ValueError(
            "--connections-every musi być większe od zera"
        )

    initialize_database()

    previous_counters = psutil.net_io_counters(pernic=True)
    previous_time = time.monotonic()
    cycle = 0

    print("Collector uruchomiony.")
    print(f"Interwał: {args.interval} s")
    print(f"Retencja: {args.retention_days} dni")
    print("Zatrzymanie: Ctrl+C")

    try:
        while True:
            time.sleep(args.interval)

            current_time = time.monotonic()
            elapsed_seconds = max(
                current_time - previous_time,
                0.001
            )

            previous_counters, traffic_rows = collect_traffic(
                previous_counters,
                elapsed_seconds,
            )

            if cycle % args.connections_every == 0:
                connection_rows = collect_connections()
            else:
                connection_rows = []

            save_samples(
                traffic_rows,
                connection_rows,
            )

            if cycle % 500 == 0:
                delete_old_samples(args.retention_days)

            total_download = sum(
                row[5] for row in traffic_rows
            )

            total_upload = sum(
                row[4] for row in traffic_rows
            )

            print(
                f"\rDOWN: {total_download / 1024:.1f} KB/s | "
                f"UP: {total_upload / 1024:.1f} KB/s | "
                f"CONNECTIONS: {len(connection_rows)}",
                end="",
                flush=True,
            )

            previous_time = current_time
            cycle += 1

    except KeyboardInterrupt:
        print("\nCollector zatrzymany.")


if __name__ == "__main__":
    main()