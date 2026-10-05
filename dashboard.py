import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from database import DB_PATH, initialize_database


st.set_page_config(
    page_title="Network Monitor",
    page_icon="🌐",
    layout="wide",
)


def format_rate(bytes_per_second: float) -> str:
    value = float(bytes_per_second or 0)

    units = [
        ("GB/s", 1024 ** 3),
        ("MB/s", 1024 ** 2),
        ("KB/s", 1024),
    ]

    for unit, divisor in units:
        if value >= divisor:
            return f"{value / divisor:.2f} {unit}"

    return f"{value:.0f} B/s"


def format_size(number_of_bytes: float) -> str:
    value = float(number_of_bytes or 0)

    units = [
        ("GB", 1024 ** 3),
        ("MB", 1024 ** 2),
        ("KB", 1024),
    ]

    for unit, divisor in units:
        if value >= divisor:
            return f"{value / divisor:.2f} {unit}"

    return f"{value:.0f} B"


def query_dataframe(query: str, parameters=()) -> pd.DataFrame:
    connection = sqlite3.connect(DB_PATH)

    try:
        return pd.read_sql_query(
            query,
            connection,
            params=parameters,
        )
    finally:
        connection.close()


def get_latest_traffic() -> pd.DataFrame:
    return query_dataframe(
        """
        SELECT
            interface,
            timestamp,
            upload_bytes_per_sec,
            download_bytes_per_sec,
            bytes_sent_total,
            bytes_recv_total
        FROM traffic_samples
        WHERE timestamp = (
            SELECT MAX(timestamp)
            FROM traffic_samples
        )
        ORDER BY download_bytes_per_sec DESC
        """
    )


def get_traffic_history(since_timestamp: str) -> pd.DataFrame:
    return query_dataframe(
        """
        SELECT
            timestamp,
            SUM(upload_bytes_per_sec) AS upload_bytes_per_sec,
            SUM(download_bytes_per_sec) AS download_bytes_per_sec
        FROM traffic_samples
        WHERE timestamp >= ?
          AND interface != 'lo'
        GROUP BY timestamp
        ORDER BY timestamp
        """,
        (since_timestamp,),
    )


def get_latest_connections() -> pd.DataFrame:
    return query_dataframe(
        """
        SELECT
            protocol,
            local_ip,
            local_port,
            remote_ip,
            remote_port,
            status,
            pid,
            COALESCE(process_name, 'unknown') AS process_name,
            timestamp
        FROM connection_samples
        WHERE timestamp = (
            SELECT MAX(timestamp)
            FROM connection_samples
        )
        ORDER BY process_name, remote_ip
        """
    )


def get_top_processes(since_timestamp: str) -> pd.DataFrame:
    return query_dataframe(
        """
        SELECT
            COALESCE(process_name, 'unknown') AS process_name,
            COUNT(*) AS observations
        FROM connection_samples
        WHERE timestamp >= ?
          AND remote_ip IS NOT NULL
        GROUP BY COALESCE(process_name, 'unknown')
        ORDER BY observations DESC
        LIMIT 15
        """,
        (since_timestamp,),
    )


def get_top_destinations(since_timestamp: str) -> pd.DataFrame:
    return query_dataframe(
        """
        SELECT
            remote_ip,
            COUNT(*) AS observations
        FROM connection_samples
        WHERE timestamp >= ?
          AND remote_ip IS NOT NULL
        GROUP BY remote_ip
        ORDER BY observations DESC
        LIMIT 15
        """,
        (since_timestamp,),
    )


def render_dashboard():
    st.title("🌐 Local Network Monitor")
    st.caption(
        "Lokalna analiza ruchu sieciowego na podstawie "
        "liczników systemowych i aktywnych połączeń."
    )

    selected_period = st.sidebar.selectbox(
        "Zakres historii",
        options=[
            "15 minut",
            "1 godzina",
            "6 godzin",
            "24 godziny",
        ],
        index=1,
    )

    period_minutes = {
        "15 minut": 15,
        "1 godzina": 60,
        "6 godzin": 360,
        "24 godziny": 1440,
    }[selected_period]

    since = (
        datetime.now(timezone.utc)
        - timedelta(minutes=period_minutes)
    ).isoformat()

    latest = get_latest_traffic()

    if latest.empty:
        st.warning(
            "Brak danych. Najpierw uruchom collector.py."
        )
        return

    excluded_interfaces = {"lo"}

    visible_latest = latest[
        ~latest["interface"].isin(excluded_interfaces)
    ]

    current_download = visible_latest[
        "download_bytes_per_sec"
    ].sum()

    current_upload = visible_latest[
        "upload_bytes_per_sec"
    ].sum()

    current_connections = get_latest_connections()

    remote_connections = current_connections[
        current_connections["remote_ip"].notna()
    ]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Download",
        format_rate(current_download),
    )

    col2.metric(
        "Upload",
        format_rate(current_upload),
    )

    col3.metric(
        "Aktywne połączenia",
        len(remote_connections),
    )

    col4.metric(
        "Procesy",
        remote_connections["process_name"].nunique(),
    )

    history = get_traffic_history(since)

    st.subheader("Ruch sieciowy")

    if history.empty:
        st.info("Brak danych dla wybranego okresu.")
    else:
        history["timestamp"] = pd.to_datetime(
            history["timestamp"],
            utc=True,
        )

        history["Download MB/s"] = (
            history["download_bytes_per_sec"]
            / 1024
            / 1024
        )

        history["Upload MB/s"] = (
            history["upload_bytes_per_sec"]
            / 1024
            / 1024
        )

        chart_data = history.set_index("timestamp")[
            ["Download MB/s", "Upload MB/s"]
        ]

        st.line_chart(chart_data)

    left, right = st.columns(2)

    with left:
        st.subheader("Procesy według liczby obserwacji")

        top_processes = get_top_processes(since)

        if not top_processes.empty:
            st.bar_chart(
                top_processes.set_index("process_name")
            )
        else:
            st.info("Brak danych o procesach.")

    with right:
        st.subheader("Najczęstsze zdalne adresy")

        destinations = get_top_destinations(since)

        if not destinations.empty:
            st.dataframe(
                destinations,
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("Brak zdalnych adresów.")

    st.subheader("Interfejsy")

    interface_table = visible_latest.copy()

    interface_table["download"] = interface_table[
        "download_bytes_per_sec"
    ].apply(format_rate)

    interface_table["upload"] = interface_table[
        "upload_bytes_per_sec"
    ].apply(format_rate)

    interface_table["received_total"] = interface_table[
        "bytes_recv_total"
    ].apply(format_size)

    interface_table["sent_total"] = interface_table[
        "bytes_sent_total"
    ].apply(format_size)

    st.dataframe(
        interface_table[
            [
                "interface",
                "download",
                "upload",
                "received_total",
                "sent_total",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Najnowsze połączenia")

    process_filter = st.text_input(
        "Filtr procesu",
        placeholder="np. chrome, python, code",
    )

    filtered_connections = current_connections.copy()

    if process_filter:
        filtered_connections = filtered_connections[
            filtered_connections["process_name"].str.contains(
                process_filter,
                case=False,
                na=False,
            )
        ]

    st.dataframe(
        filtered_connections,
        width="stretch",
        hide_index=True,
    )

    newest_timestamp = latest["timestamp"].max()

    st.caption(
        f"Ostatnia próbka: {newest_timestamp} UTC"
    )


initialize_database()

st.sidebar.header("Sterowanie")
st.sidebar.write(f"Baza: `{DB_PATH.name}`")

if st.sidebar.button("Odśwież teraz"):
    st.rerun()

render_dashboard()