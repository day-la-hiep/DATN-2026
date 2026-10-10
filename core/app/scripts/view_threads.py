import threading

for thread in threading.enumerate():
    print(
        f"- Tên: {thread.name} | ID (Ident): {thread.ident} | Đang sống:"
        f" {thread.is_alive()}"
    )
