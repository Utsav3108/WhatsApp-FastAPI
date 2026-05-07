import asyncio
import socketio

sio = socketio.AsyncClient()

@sio.event
async def connect():
    print("Connected to server")
    # 1. Join after connecting
    await sio.emit('join', {'user_id': 1})

@sio.on('receive_message')
async def on_message(data):
    print(f"Received from Gemini: {data}")

async def main():
    await sio.connect('http://localhost:8000')
    
    # 2. Send a message
    payload = {
        "sender_id": 1, 
        "receiver_id": 2, 
        "text": "Tell me a joke"
    }
    await sio.emit('send_message', payload)
    
    # Keep the connection alive to wait for Gemini's response
    await sio.wait()

if __name__ == '__main__':
    asyncio.run(main())