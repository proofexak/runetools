"""python -m dashboard [--port 8777] [--no-browser]"""
import argparse, webbrowser

from dashboard.server import serve


def main():
    parser = argparse.ArgumentParser(prog="python -m dashboard")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    httpd, _ = serve(args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Dashboard on {url} (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
