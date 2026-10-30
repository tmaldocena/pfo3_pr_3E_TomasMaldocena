"""Cliente de tareas.

Envía tareas al servidor por socket y muestra los resultados a medida que llegan.

Uso:
    python client.py                              # corre un set de tareas de demo
    python client.py -t fib:30 -t prime:97 -t upper:hola -t "sum:[1,2,3]"
    python client.py --host 127.0.0.1 --port 9000 -t sleep:2
"""
import argparse
import json
import socket
import time

DEMO_TASKS = [
    "fib:30", "fib:500", "prime:97", "prime:1000003", "sum:[1,2,3,4,5]",
    "upper:hola mundo", "reverse:maguito", "sleep:1", "sleep:2", "fib:abc", "inexistente:1",
]


def parse_task(text, task_id):
    """'tipo:payload' -> dict. El payload se interpreta como JSON si se puede
    (30, [1,2,3]); si no, como texto plano."""
    task_type, _, raw = text.partition(":")
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = raw
    return {"id": task_id, "type": task_type, "payload": payload}


def main():
    parser = argparse.ArgumentParser(description="Cliente de tareas")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("-t", "--task", action="append", metavar="TIPO:PAYLOAD",
                        help="tarea a enviar (se puede repetir). Sin -t se usa un set de demo")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="segundos máximos de espera por resultados")
    args = parser.parse_args()

    tasks = [parse_task(t, i) for i, t in enumerate(args.task or DEMO_TASKS, start=1)]

    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sent_at = {}
        for task in tasks:
            sent_at[task["id"]] = time.perf_counter()
            sock.sendall((json.dumps(task) + "\n").encode("utf-8"))
        print(f"Enviadas {len(tasks)} tareas a {args.host}:{args.port}\n")

        pending = {t["id"]: t for t in tasks}
        with sock.makefile("r", encoding="utf-8") as reader:
            while pending:
                try:
                    line = reader.readline()
                except socket.timeout:
                    print(f"\nTimeout: faltan {len(pending)} resultados")
                    break
                if not line:
                    print("\nEl servidor cerró la conexión")
                    break

                reply = json.loads(line)
                task = pending.pop(reply.get("id"), None)
                label = f"{task['type']}:{task['payload']}" if task else "?"
                total = time.perf_counter() - sent_at.get(reply.get("id"), time.perf_counter())
                outcome = reply.get("result") if reply["status"] == "ok" else f"ERROR: {reply.get('error')}"
                text = str(outcome)
                if len(text) > 60:
                    text = text[:57] + "..."
                print(f"[#{reply.get('id')}] {label:<24} -> {text}  "
                      f"({reply.get('worker')}, {total:.2f}s total)")


if __name__ == "__main__":
    main()
