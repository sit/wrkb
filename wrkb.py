import argparse


def main():
    parser = argparse.ArgumentParser(description="wrkb - a command line tool")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    args = parser.parse_args()

    print("Hello from wr!")

if __name__ == "__main__":
    main()
