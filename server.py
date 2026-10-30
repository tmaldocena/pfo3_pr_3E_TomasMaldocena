"""Servidor de tareas.

Recibe tareas por socket TCP (JSON, un mensaje por línea), las encola y las
distribuye a un grupo de workers. Cada worker devuelve el resultado al cliente
que envió la tarea.

Arquitectura (simplificada del diagrama):
    Clientes --> [Servidor: acepta conexiones] --> Cola --> Workers (hilos)
                                                              |
                                                  resultado --+--> Cliente
"""
import argparse
import json
import logging
import queue
import socket
import threading
import time

log = logging.getLogger("server")

# ----------------------------------------------------------------------------
# Tareas disponibles
# ----------------------------------------------------------------------------


def fib(n):
    n = int(n)
    if not 0 <= n <= 10_000:
        raise ValueError("n debe estar entre 0 y 10000")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def is_prime(n):
    n = int(n)
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def sleep_task(seconds):
    seconds = float(seconds)
    if not 0 <= seconds <= 10:
        raise ValueError("seconds debe estar entre 0 y 10")
    time.sleep(seconds)  # simula trabajo pesado
    return f"dormí {seconds}s"


TASKS = {
    "fib": fib,                                   # fib:30
    "prime": is_prime,                            # prime:97
    "sum": lambda xs: sum(xs),                    # sum:[1,2,3]
    "upper": lambda s: str(s).upper(),            # upper:hola
    "reverse": lambda s: str(s)[::-1],            # reverse:hola
    "sleep": sleep_task,                          # sleep:2
}

# ----------------------------------------------------------------------------
# Conexión de cliente
# ----------------------------------------------------------------------------


class Connection:
    """Envuelve un socket de cliente. El lock evita que dos workers mezclen
    sus respuestas si contestan al mismo cliente a la vez."""

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self._lock = threading.Lock()

    def send(self, msg):
        data = (json.dumps(msg) + "\n").encode("utf-8")
        with self._lock:
            try:
                self.sock.sendall(data)
            except OSError:
                log.warning("No pude responder a %s (desconectado)", self.addr)


# ----------------------------------------------------------------------------
# Workers
# ----------------------------------------------------------------------------


def worker_loop(name, tasks, stop):
    while not stop.is_set():
        try:
            conn, task = tasks.get(timeout=0.5)
        except queue.Empty:
            continue

        task_id = task.get("id")
        started = time.perf_counter()
        try:
            func = TASKS.get(task.get("type"))
            if func is None:
                raise ValueError(f"tipo de tarea desconocido: {task.get('type')!r}")
            result = func(task.get("payload"))
            reply = {"id": task_id, "status": "ok", "result": result}
        except Exception as exc:  # noqa: BLE001 - devolvemos cualquier error al cliente
            reply = {"id": task_id, "status": "error", "error": str(exc)}

        reply["worker"] = name
        reply["elapsed"] = round(time.perf_counter() - started, 4)
        log.info("%s terminó tarea %s de %s -> %s", name, task_id, conn.addr, reply["status"])
        conn.send(reply)
        tasks.task_done()


# ----------------------------------------------------------------------------
# Atención de clientes
# ----------------------------------------------------------------------------


def handle_client(conn, tasks):
    log.info("Cliente conectado: %s", conn.addr)
    try:
        with conn.sock, conn.sock.makefile("r", encoding="utf-8") as reader:
            for line in reader:
                line = line.strip()
                if not line:
                    continue
                try:
                    task = json.loads(line)
                    if not isinstance(task, dict):
                        raise ValueError("la tarea debe ser un objeto JSON")
                except ValueError as exc:
                    conn.send({"id": None, "status": "error", "error": f"mensaje inválido: {exc}"})
                    continue
                tasks.put((conn, task))  # bloquea si la cola está llena (backpressure)
    except OSError:
        pass
    finally:
        log.info("Cliente desconectado: %s", conn.addr)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Servidor de tareas con workers")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--workers", type=int, default=4, help="cantidad de workers")
    parser.add_argument("--queue-size", type=int, default=1000, help="tamaño máximo de la cola")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(threadName)s] %(message)s",
                        datefmt="%H:%M:%S")

    tasks = queue.Queue(maxsize=args.queue_size)
    stop = threading.Event()

    for i in range(1, args.workers + 1):
        threading.Thread(target=worker_loop, args=(f"Worker-{i}", tasks, stop),
                         name=f"Worker-{i}", daemon=True).start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen()
    server.settimeout(1.0)  # para poder revisar `stop` y salir con Ctrl+C
    log.info("Servidor escuchando en %s:%s con %s workers", args.host, args.port, args.workers)

    try:
        while not stop.is_set():
            try:
                sock, addr = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=handle_client, args=(Connection(sock, addr), tasks),
                             name=f"Client-{addr[1]}", daemon=True).start()
    except KeyboardInterrupt:
        log.info("Apagando servidor...")
    finally:
        stop.set()
        server.close()


if __name__ == "__main__":
    main()
