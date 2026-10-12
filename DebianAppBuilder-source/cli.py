import argparse
def main(argv=None):
    parser = argparse.ArgumentParser(description="Debian App Builder CLI")
    parser.add_argument(
        "--version",
        action="version",
        version="Debian App Builder CLI",
    )
    parser.parse_args(argv)
    print('''THIS PROJECT IS OPEN-SOURCE, YOU CAN MODIFY, DISTRIBUTE AND USE IT FREELY.\nHowever you must credit the original author and the project repository if you use it in your own project.\nSincerely tuffgit21\nsite:https://tuffgit21.is-a.dev/\nGithub repository:https://github.com/tuffgit21/Debian-App-Builder/ 
    ''')
    print("Debian App Builder CLI selected.")
    print("Package-building commands are not implemented yet.")
    print("Expect CLI version release with v4.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())