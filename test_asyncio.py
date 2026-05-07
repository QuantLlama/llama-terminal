import asyncio
import sys

async def test():
    try:
        print(f"Python version: {sys.version}")
        print(f"Asyncio subprocess available: {hasattr(asyncio, 'subprocess')}")
        if hasattr(asyncio, 'subprocess'):
             print(f"PIPE: {asyncio.subprocess.PIPE}")
        
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-Command", "echo Hello",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        print(f"Stdout: {stdout.decode().strip()}")
        print(f"Return code: {proc.returncode}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
