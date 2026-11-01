from pyrogram import Client
from scheduler import scheduler  # registers handlers

app = Client(
    "myuserbot",
    api_id=,37550071          # my.telegram.org se
    api_hash="eca739f28db4f12737a0d418f4a77343"",
    plugins=dict(root="."),
)

if __name__ == "__main__":
    app.run()
