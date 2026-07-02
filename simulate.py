import asyncio
import random
import time
import socketio

SERVER_URL = "http://localhost:8000"
SOCKET_PATH = "/socket.io"

# Existing persona IDs in your database
PERSONAS = [2, 3, 4]

# Users that will simulate chatting
USERS = [3, 5, 7]

# Test duration
DURATION_SECONDS = 25 * 60

# Average interval between messages
MSG_INTERVAL = 3


async def simulate_user(user_id: int):
    sio = socketio.AsyncSimpleClient()

    try:
        # Stagger startup slightly
        await asyncio.sleep((user_id % 3) * 0.5)

        await sio.connect(
            SERVER_URL,
            socketio_path=SOCKET_PATH,
            wait_timeout=10
        )

        print(f"[User {user_id}] Connected")

        await sio.emit("join", {
            "user_id": user_id
        })

        start = time.time()
        msg_count = 0

        while time.time() - start < DURATION_SECONDS:

            receiver = random.choice(PERSONAS)

            await sio.emit("send_message", {
                "sender_id": user_id,
                "receiver_id": receiver,
                "text": f"Load test message {msg_count} from user {user_id}"
            })

            msg_count += 1

            if msg_count % 10 == 0:
                print(f"[User {user_id}] Sent {msg_count} messages")

            # Small randomization to simulate humans
            await asyncio.sleep(
                MSG_INTERVAL + random.uniform(-0.5, 0.5)
            )

            # Occasionally reconnect
            if random.random() < 0.03:
                print(f"[User {user_id}] Reconnecting...")

                await sio.disconnect()
                await asyncio.sleep(1)

                await sio.connect(
                    SERVER_URL,
                    socketio_path=SOCKET_PATH,
                    wait_timeout=10
                )

                await sio.emit("join", {
                    "user_id": user_id
                })

        print(f"[User {user_id}] Finished ({msg_count} messages)")

    except Exception as e:
        print(f"[User {user_id}] ERROR: {e}")

    finally:
        try:
            await sio.disconnect()
        except Exception:
            pass


async def main():
    print(f"Starting load test with {len(USERS)} users...")
    await asyncio.gather(*(simulate_user(user) for user in USERS))
    print("Load test complete.")


if __name__ == "__main__":
    asyncio.run(main())