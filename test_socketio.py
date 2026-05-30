import asyncio
import socketio
from datetime import datetime

sio = socketio.AsyncClient()

CHALLENGE_SESSION_ID = 11
CHALLENGE_ID = 'ask_for_date_3'
SENDER_ID = 1
RECEIVER_ID = 11

# 5 minutes
CHALLENGE_DURATION_SECONDS = 300

challenge_completed = False


# -------------------------------------------------------------------
# CONNECTION EVENTS
# -------------------------------------------------------------------

@sio.event
async def connect():

    print("Connected to server")

    # Associate socket with user
    await sio.emit(
        'join',
        {
            'user_id': SENDER_ID
        }
    )

    # Join challenge room
    await sio.emit(
        'join_challenge',
        {
            'challenge_session_id': CHALLENGE_SESSION_ID
        }
    )

    print(f"Joined challenge session {CHALLENGE_SESSION_ID}")

    # Request session sync
    await sio.emit(
        'request_session_sync',
        {
            'challenge_session_id': CHALLENGE_SESSION_ID
        }
    )

    # Send first message
    await sio.emit(
        'send_message',
        {
            'challenge_session_id': CHALLENGE_SESSION_ID,
            'sender_id': SENDER_ID,
            'receiver_id': RECEIVER_ID,
            'text': 'Hello there',
            'challenge_id': CHALLENGE_ID
        }
    )


@sio.event
async def disconnect():

    print("Disconnected from server")


# -------------------------------------------------------------------
# RECEIVE EVENTS
# -------------------------------------------------------------------

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

    global challenge_completed

    challenge_completed = True

    print("\n=== CHALLENGE COMPLETED ===")
    print(data)

    status = data.get("status")

    print(f"Challenge Result: {status}")

    # Optional disconnect after completion
    await asyncio.sleep(2)

    await sio.disconnect()


@sio.on('error')
async def on_error(data):

    print("\n=== ERROR ===")
    print(data)


# -------------------------------------------------------------------
# TEST MESSAGE SIMULATION
# -------------------------------------------------------------------

async def send_test_messages():

    await asyncio.sleep(5)

    messages = []

    for text in messages:

        if challenge_completed:
            return

        payload = {
            'challenge_session_id': CHALLENGE_SESSION_ID,
            'sender_id': SENDER_ID,
            'receiver_id': RECEIVER_ID,
            'text': text,
            'challenge_id': CHALLENGE_ID
        }

        print(f"\nSending: {text}")

        await sio.emit('send_message', payload)

        await asyncio.sleep(8)


# -------------------------------------------------------------------
# HEARTBEAT
# -------------------------------------------------------------------

async def heartbeat():

    while True:

        if challenge_completed:
            return

        await sio.emit(
            'ping',
            {
                'challenge_session_id': CHALLENGE_SESSION_ID
            }
        )

        print("Ping sent")

        await asyncio.sleep(20)


# -------------------------------------------------------------------
# AUTO COMPLETE CHALLENGE AFTER 5 MINUTES
# -------------------------------------------------------------------

async def auto_complete_challenge():

    global challenge_completed

    print(
        f"\nChallenge timer started "
        f"({CHALLENGE_DURATION_SECONDS} seconds)"
    )

    await asyncio.sleep(CHALLENGE_DURATION_SECONDS)

    if challenge_completed:
        return

    print("\nEmitting complete_challenge event")

    payload = {
        'challenge_session_id': CHALLENGE_SESSION_ID,
        'status': 'lost_timeout',
        'reason': 'Challenge time expired',
        'user_id': SENDER_ID,
        'challenge_id': CHALLENGE_ID
    }

    await sio.emit(
        'complete_challenge',
        payload
    )


# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------


async def main():

    await sio.connect(
        'http://localhost:8000',
        transports=['websocket']
    )

    asyncio.create_task(send_test_messages())

    asyncio.create_task(heartbeat())

    asyncio.create_task(auto_complete_challenge())

    await sio.wait()


if __name__ == '__main__':

    asyncio.run(main())