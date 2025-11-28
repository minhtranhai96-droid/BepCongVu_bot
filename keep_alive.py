import time
import threading
import requests
import os

URL = os.getenv("KEEP_ALIVE_URL")  # lấy URL từ ENV cho dễ đổi

def keep_alive():
    def run():
        while True:
            try:
                print("⚡ Sending keep-alive ping...")
                requests.get(f"{URL}/ping")
            except Exception as e:
                print("⚠️ Error pinging server:", e)
            time.sleep(600)  # 600 giây = 10 phút
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
