# PFO 3 - Rediseño como Sistema Distribuido (Cliente-Servidor) - PSR 3E

Implementación en Python de un sistema cliente-servidor en el que un **servidor** recibe tareas por **sockets TCP**, las encola y las distribuye a un grupo de **workers** que las procesan en paralelo. Un **cliente** envía las tareas y recibe los resultados.

Solo usa la librería estándar de Python, no hay dependencias que instalar.

## Arquitectura

El diseño completo del sistema distribuido es el siguiente. Las capas de **Clientes**, **Servidores (workers)** y **Mensajería (cola)** están implementadas en este proyecto; el balanceo se resuelve con una cola compartida y el almacenamiento queda como extensión futura (ver [Alcance](#alcance)).

```mermaid
graph LR
    subgraph Capa_Cliente [" 👥 Clientes "]
        C1([Cliente Web])
        C2([Cliente Móvil])
    end

    subgraph Capa_Balanceo [" ⚖️ Balanceo "]
        LB{{Balanceador de Carga<br/>Nginx / HAProxy}}
    end

    subgraph Capa_Procesamiento [" ⚙️ Servidores "]
        W1(Worker 1<br/>Thread Pool)
        W2(Worker 2<br/>Thread Pool)
        W3(Worker N<br/>Thread Pool)
    end

    subgraph Capa_Mensajeria [" 📨 Mensajería "]
        MQ[(RabbitMQ<br/>Cola de Mensajes)]
    end

    subgraph Capa_Almacenamiento [" 💾 Almacenamiento "]
        DB[(PostgreSQL<br/>Base de Datos)]
        S3[(S3 Bucket<br/>Archivos)]
    end

    C1 ==>|HTTP/HTTPS| LB
    C2 ==>|HTTP/HTTPS| LB

    LB -->|Distribuye Tráfico| W1
    LB -->|Distribuye Tráfico| W2
    LB -->|Distribuye Tráfico| W3

    W1 <-->|Pub/Sub| MQ
    W2 <-->|Pub/Sub| MQ
    W3 <-->|Pub/Sub| MQ

    W1 -->|Lectura/Escritura| DB
    W2 -->|Lectura/Escritura| DB
    W3 -->|Lectura/Escritura| DB

    W1 -.->|Subida/Descarga| S3
    W2 -.->|Subida/Descarga| S3
    W3 -.->|Subida/Descarga| S3

    classDef cliente fill:#e0e7ff,stroke:#4f46e5,stroke-width:2px,color:#1e1b4b;
    classDef balanceo fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f;
    classDef worker fill:#cffafe,stroke:#0891b2,stroke-width:2px,color:#164e63;
    classDef cola fill:#ffe4e6,stroke:#e11d48,stroke-width:2px,color:#881337;
    classDef storage fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d;

    class C1,C2 cliente;
    class LB balanceo;
    class W1,W2,W3 worker;
    class MQ cola;
    class DB,S3 storage;

    style Capa_Cliente fill:#f5f7ff,stroke:#a5b4fc,stroke-dasharray:6 4
    style Capa_Balanceo fill:#fffbeb,stroke:#fcd34d,stroke-dasharray:6 4
    style Capa_Procesamiento fill:#ecfeff,stroke:#67e8f9,stroke-dasharray:6 4
    style Capa_Mensajeria fill:#fff1f2,stroke:#fda4af,stroke-dasharray:6 4
    style Capa_Almacenamiento fill:#f0fdf4,stroke:#86efac,stroke-dasharray:6 4

    linkStyle 0,1 stroke:#4f46e5,stroke-width:3px
    linkStyle 2,3,4 stroke:#d97706,stroke-width:2px
    linkStyle 5,6,7 stroke:#e11d48,stroke-width:2px
    linkStyle 8,9,10 stroke:#16a34a,stroke-width:2px
    linkStyle 11,12,13 stroke:#16a34a,stroke-width:2px,stroke-dasharray:4 4
```

### Cómo se implementó

| Componente del diagrama | En este proyecto |
|---|---|
| Clientes | `client.py`: se conecta por socket TCP, envía tareas y muestra los resultados. |
| Balanceador de carga | La **cola compartida**: cada worker libre toma la siguiente tarea, lo que reparte la carga de forma natural. |
| Cola de mensajes (RabbitMQ) | `queue.Queue` de la librería estándar, con tamaño máximo configurable (aplica *backpressure* cuando se llena). |
| Workers (Thread Pool) | Hilos (`threading.Thread`) que consumen tareas de la cola y devuelven el resultado al cliente que la envió. |

## Flujo de una tarea

```mermaid
sequenceDiagram
    participant C as Cliente
    participant S as Servidor
    participant Q as Cola
    participant W as Worker

    C->>S: {"id": 1, "type": "fib", "payload": 30}
    S->>Q: encola la tarea
    Q->>W: entrega al primer worker libre
    W->>W: ejecuta la tarea
    W-->>C: {"id": 1, "status": "ok", "result": 832040, "worker": "Worker-1"}
```

## Estructura del proyecto

```
.
├── server.py   # Servidor: acepta conexiones, encola tareas y administra los workers
├── client.py   # Cliente: envía tareas y recibe resultados
└── README.md
```

## Requisitos

- Python 3.8 o superior
- Ninguna dependencia externa

## Uso

### 1. Iniciar el servidor

```bash
python server.py --workers 4
```

| Opción | Por defecto | Descripción |
|---|---|---|
| `--host` | `127.0.0.1` | Dirección donde escucha el servidor |
| `--port` | `9000` | Puerto TCP |
| `--workers` | `4` | Cantidad de workers |
| `--queue-size` | `1000` | Tamaño máximo de la cola |

Para detenerlo, `Ctrl+C`.

### 2. Ejecutar el cliente

```bash
# Set de tareas de demostración
python client.py

# Tareas propias (formato TIPO:PAYLOAD, se puede repetir -t)
python client.py -t fib:30 -t prime:97 -t upper:hola -t "sum:[1,2,3]" -t sleep:2
```

| Opción | Por defecto | Descripción |
|---|---|---|
| `--host` | `127.0.0.1` | Dirección del servidor |
| `--port` | `9000` | Puerto del servidor |
| `-t`, `--task` | set de demo | Tarea a enviar (`TIPO:PAYLOAD`) |
| `--timeout` | `30` | Segundos máximos de espera por los resultados |

El payload se interpreta como JSON si es posible (`30`, `[1,2,3]`); si no, como texto.

### Ejemplo de salida

```
Enviadas 11 tareas a 127.0.0.1:9000

[#1] fib:30                   -> 832040  (Worker-1, 0.00s total)
[#3] prime:97                 -> True  (Worker-1, 0.00s total)
[#6] upper:hola mundo         -> HOLA MUNDO  (Worker-1, 0.00s total)
[#10] fib:abc                 -> ERROR: invalid literal for int() with base 10: 'abc'  (Worker-1, 0.00s total)
[#8] sleep:1                  -> dormí 1.0s  (Worker-2, 1.00s total)
[#9] sleep:2                  -> dormí 2.0s  (Worker-3, 2.00s total)
```

Los resultados llegan en el orden en que los workers terminan, no en el de envío; por eso cada mensaje lleva un `id`.

## Tareas disponibles

| Tipo | Payload | Descripción |
|---|---|---|
| `fib` | entero `0-10000` | Número de Fibonacci |
| `prime` | entero | Indica si es primo |
| `sum` | lista de números | Suma los elementos |
| `upper` | texto | Convierte a mayúsculas |
| `reverse` | texto | Invierte el texto |
| `sleep` | segundos `0-10` | Simula trabajo pesado |

Para agregar una tarea nueva, se define una función en `server.py` y se registra en el diccionario `TASKS`.

## Protocolo

Mensajes JSON, uno por línea (`\n`), sobre TCP.

**Solicitud (cliente → servidor)**

```json
{"id": 1, "type": "fib", "payload": 30}
```

**Respuesta (servidor → cliente)**

```json
{"id": 1, "status": "ok", "result": 832040, "worker": "Worker-1", "elapsed": 0.0001}
```

```json
{"id": 10, "status": "error", "error": "tipo de tarea desconocido: 'inexistente'", "worker": "Worker-2", "elapsed": 0.0}
```

Si el servidor recibe un mensaje que no es JSON válido, responde con `status: "error"` y mantiene la conexión abierta.

## Decisiones de diseño

- **Un hilo por conexión de cliente:** el servidor atiende varios clientes a la vez.
- **Lock por conexión:** evita que dos workers mezclen sus respuestas al escribir en el mismo socket.
- **Cola con tamaño máximo:** si los clientes envían más rápido de lo que los workers procesan, el servidor frena la lectura en lugar de agotar la memoria.
- **Errores aislados:** una excepción dentro de una tarea se devuelve al cliente como error y no afecta al worker ni al servidor.

## Alcance

Implementado:

- Servidor que recibe tareas por socket y las distribuye a workers
- Cliente que envía tareas y recibe resultados
- Cola de tareas con balanceo natural entre workers
- Manejo de errores y de mensajes inválidos

Fuera de alcance (presentes en el diagrama como diseño objetivo):

- Persistencia en PostgreSQL y almacenamiento de archivos en S3
- Balanceador de carga externo (Nginx / HAProxy) y broker de mensajes dedicado (RabbitMQ)
- Workers como procesos independientes: al usar hilos, las tareas que consumen mucho CPU están limitadas por el GIL de Python
