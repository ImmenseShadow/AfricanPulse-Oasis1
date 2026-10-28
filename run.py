from config.settings import HOST, PORT
from src.app import create_app

app = create_app()

if __name__ == "__main__":
    print(f"AfricanPulse Oasis running at http://{HOST}:{PORT}  (press Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, debug=False)