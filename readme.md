# Local Network Monitor

Local Network Monitor is a lightweight, local dashboard for observing network
traffic and active internet connections on your computer.

The project uses:

- **psutil** to read network counters and active connections
- **SQLite** to store recent samples
- **pandas** to prepare dashboard data
- **Streamlit** to display traffic, interfaces, processes, and remote addresses

All monitoring data stays on the computer where the application runs.

## Features

- Current download and upload rates
- Traffic history for the last 15 minutes, 1 hour, 6 hours, or 24 hours
- Active remote connection count
- Processes grouped by connection observations
- Most frequently observed remote IP addresses
- Per-interface transfer rates and cumulative byte counters
- Searchable list of the latest connections
- Automatic deletion of old samples

## How it works

The application has two processes:

1. `collector.py` samples network statistics and connections, then writes them
   to `network_monitor.db`.
2. `dashboard.py` reads the database and presents the collected information in
   a Streamlit web dashboard.

Both processes must run at the same time for the dashboard to receive new data.

## Requirements

- Python 3.10 or newer
- A terminal with permission to inspect network connections
- A modern web browser

Some operating systems restrict process and connection details. Run the
collector as Administrator on Windows or with `sudo` on Linux/macOS if process
names or connections are missing.

## Tutorial

### 1. Open the project

In PowerShell, change to the project directory:

```powershell
cd "C:\path\to\local-network-monitor"
```

### 2. Create a virtual environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, allow local scripts for the current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then run the activation command again.

On Linux or macOS, activate the environment with:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Start the collector

In the first terminal:

```powershell
python collector.py
```

The default configuration:

- Collects traffic every 2 seconds
- Collects active connections every 5 cycles
- Keeps 7 days of history

Leave this terminal running. Stop the collector with `Ctrl+C`.

### 5. Start the dashboard

Open a second terminal in the project directory, activate the same virtual
environment, and run:

```powershell
streamlit run dashboard.py
```

Streamlit normally opens the dashboard automatically. If it does not, open the
local URL shown in the terminal, usually:

```text
http://localhost:8501
```

### 6. Use the dashboard

Use the sidebar to:

- Select the traffic history period
- Refresh the displayed data immediately

The dashboard shows:

- **Download** and **Upload**: combined current rate across visible interfaces
- **Active connections**: latest connections with a remote address
- **Processes**: number of unique processes in the latest sample
- **Network traffic**: upload and download history
- **Interfaces**: current rates and cumulative totals per network interface
- **Latest connections**: protocol, endpoints, state, PID, and process name

Enter part of a process name, such as `chrome`, `python`, or `code`, in the
process filter to narrow the latest-connections table.

## Collector configuration

Use command-line options to change sampling and retention:

```powershell
python collector.py --interval 1 --connections-every 10 --retention-days 14
```

| Option | Default | Description |
|---|---:|---|
| `--interval` | `2.0` | Seconds between traffic samples |
| `--connections-every` | `5` | Collect connections every N sampling cycles |
| `--retention-days` | `7` | Number of days to keep historical data |

Lower intervals provide finer-grained data but increase database writes and
storage usage.

## Data storage and privacy

Samples are stored in `network_monitor.db` in the project directory. The
database can contain:

- Network interface names and traffic counters
- Local and remote IP addresses and ports
- Process IDs and process names
- UTC timestamps

The application does not upload this information. Treat the database as
sensitive because connection history may reveal network activity.

To reset all history:

1. Stop the collector and dashboard.
2. Delete `network_monitor.db` and any associated
   `network_monitor.db-shm` or `network_monitor.db-wal` files.
3. Restart the collector or dashboard; the database schema will be recreated.

## Project structure

```text
local-network-monitor/
|-- collector.py       # Samples traffic and connections
|-- dashboard.py       # Streamlit dashboard
|-- database.py        # SQLite path, schema, and connection helper
|-- requirements.txt   # Python dependencies
|-- network_monitor.db # Local data, created at runtime
`-- readme.md
```

## Troubleshooting

### The dashboard says there is no data

Start `collector.py`, wait for at least one sampling interval, and refresh the
dashboard.

### Connections or process names are missing

Stop the collector and restart the terminal as Administrator on Windows. On
Linux or macOS, try:

```bash
sudo .venv/bin/python collector.py
```

### Port 8501 is already in use

Choose another Streamlit port:

```powershell
streamlit run dashboard.py --server.port 8502
```

### The database is locked

Stop duplicate collector instances. The application uses SQLite WAL mode and a
busy timeout, but multiple collectors writing concurrently are unnecessary.

### The displayed traffic looks duplicated

Virtual adapters, VPNs, and container interfaces may report traffic separately.
Review the **Interfaces** table to identify which adapters contribute to the
total.

## Stop the application

Press `Ctrl+C` in both terminals: once for the collector and once for
Streamlit.
