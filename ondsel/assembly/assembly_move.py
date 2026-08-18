import importlib

from ondsel.assembly import assembly_pull

assembly_pull = importlib.reload(assembly_pull)
RunCommand = assembly_pull.RunCommand


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
