# import asyncio
# import socketio

# sio = socketio.AsyncClient()

# @sio.event
# async def connect():
#     print("Connected to server")
#     # 1. Join after connecting
#     await sio.emit('join', {'user_id': 1})

# @sio.on('receive_message')
# async def on_message(data):
#     print(f"Received from Gemini: {data}")

# async def main():
#     await sio.connect('http://localhost:8000')
    
#     # 2. Send a message
#     payload = {
#         "sender_id": 1, 
#         "receiver_id": 2, 
#         "text": "Tell me a joke"
#     }
#     await sio.emit('send_message', payload)
    
#     # Keep the connection alive to wait for Gemini's response
#     await sio.wait()

# if __name__ == '__main__':
#     asyncio.run(main())

import asyncio
import socketio

sio = socketio.AsyncClient()

CHALLENGE_SESSION_ID = 4
SENDER_ID = 1
RECEIVER_ID = 2

@sio.event
async def connect():
    print("Connected to server")

    # Old join event
    await sio.emit('join', {
        'user_id': SENDER_ID
    })

    # Challenge session join
    await sio.emit('join_challenge', {
        'challenge_session_id': CHALLENGE_SESSION_ID
    })

    print("Joined challenge session")

    # Optional: request sync after join
    await sio.emit('request_session_sync', {
        'challenge_session_id': CHALLENGE_SESSION_ID
    })

    # Send first challenge message
    await sio.emit('send_message', {
        'challenge_session_id': CHALLENGE_SESSION_ID,
        'text': 'Hello there',
        "sender_id": SENDER_ID,
      "receiver_id": RECEIVER_ID,
    })



@sio.event
async def disconnect():
    print("Disconnected from server")


@sio.on('receive_message')
async def on_receive_message(data):
    print("\n=== RECEIVE MESSAGE ===")
    print(data)


@sio.on('typing')
async def on_typing(data):
    print("\n=== TYPING EVENT ===")
    print(data)


@sio.on('session_sync')
async def on_session_sync(data):
    print("\n=== SESSION SYNC ===")
    print(data)

    remaining_seconds = data.get("remaining_seconds")
    status = data.get("status")

    print(f"Remaining Seconds: {remaining_seconds}")
    print(f"Status: {status}")


@sio.on('challenge_completed')
async def on_challenge_completed(data):
    print("\n=== CHALLENGE COMPLETED ===")
    print(data)

    status = data.get("status")

    print(f"Challenge Result: {status}")


@sio.on('error')
async def on_error(data):
    print("\n=== ERROR ===")
    print(data)


async def send_test_messages():
    """
    Simulates user sending messages continuously
    """

    await asyncio.sleep(5)

    messages = [
        "You seem interesting",
        "What do you usually do on weekends?",
        "I think we'd get along well"
    ]

    for text in messages:

        payload = {
        'challenge_session_id': CHALLENGE_SESSION_ID,
        'text': text,
        "sender_id": SENDER_ID,
      "receiver_id": RECEIVER_ID,
    }

        print(f"\nSending: {text}")

        await sio.emit('send_message', payload)

        await asyncio.sleep(8)


async def heartbeat():
    """
    Optional heartbeat ping
    """

    while True:

        await sio.emit('ping', {
            'challenge_session_id': CHALLENGE_SESSION_ID
        })

        print("Ping sent")

        await asyncio.sleep(20)


async def main():

    await sio.connect(
        'http://localhost:8000',
        transports=['websocket']
    )

    asyncio.create_task(send_test_messages())

    asyncio.create_task(heartbeat())

    await sio.wait()


if __name__ == '__main__':
    asyncio.run(main())