import typer

app = typer.Typer()

@app.command()
def version():
    """Show Aether version"""
    from aether import __version__
    print(f"Aether v{__version__}")

if __name__ == "__main__":
    app()
