# Ops Center agent

A tiny program that measures the computer it runs on (CPU, memory, disk) and reports to an Ops Center
server every few seconds. **It is independent of the server code**: copy this folder to any machine
(Windows, Linux, macOS), you only need Python 3.9+ and `psutil`.

## 1. Get an API key

In Ops Center open **Hosts → Add host**. The key (`ops_...`) is shown **once** - copy it now.
(Lost it? Delete the host and add it again.)

## 2. Run it

```
pip install -r requirements.txt          # or: python -m venv .venv  first, if you like
python agent.py --url http://127.0.0.1:8000 --key-file key.txt
```

Put the key into `key.txt` (just the key, nothing else). `--key ops_...` works too, but then the key is
visible to everyone on the machine in the process list. The key can also come from the environment:
`OPS_KEY` / `OPS_KEY_FILE`, and the rest from `OPS_URL` / `OPS_INTERVAL`.

| option | meaning |
|---|---|
| `--url` | server address (use `https://` as soon as it is not your own computer) |
| `--key-file`, `--key` | the API key |
| `--every` | seconds between reports (default 5, minimum 1) |
| `--once` | send a single report and exit (cron, tests) |

## Behaviour

- **Server down / network gone:** it keeps trying with growing pauses (up to 60 s) and continues by itself.
- **Key rejected (HTTP 401/403):** it stops with exit code **2** - retrying cannot help (wrong key, or the host was deleted).
- **Ctrl+C or SIGTERM:** stops cleanly.

## Run it permanently

- **Linux:** `opsagent.service` (systemd) - the steps are written at the top of the file.
- **Windows:** Task Scheduler → "Create task" → trigger "At log on" → action: `pythonw.exe C:\path\agent.py --key-file C:\path\key.txt`.
