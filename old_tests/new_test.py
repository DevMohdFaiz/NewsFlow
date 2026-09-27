from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def main(name: str)->str:
    print(name)
    return f"Hello {name}"

if __name__== "__main__":
    main(name="Faiz")
