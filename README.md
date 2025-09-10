# ds-fastapi

## Install

```sh
uv add git+https://github.com/wamdata/ds-fastapi
```

## Update

```sh
uv add -U ds-fastapi
```

## Usage

```python
from fastapi import Depends
from ds_fastapi import EnhancedFastAPI

# when debug is True, tracebacks will be included in the error response
app = EnhancedFastAPI(debug=True)

# Optional: a dependency with documented error responses
class Auth:
    def __call__(self):
        # ... validate auth here, or raise HTTPException(status_code=401) ...
        return True
    
    # Document dependency errors so EnhancedFastAPI can merge into OpenAPI
    responses = {401: {"description": "Unauthorized"}}


require_auth = Auth()


@app.get("/hello", dependencies=[Depends(require_auth)])
def hello():
    return {"message": "world"}

# Example endpoint that triggers a 500 to see standardized error shape
@app.get("/boom")
def boom():
    raise RuntimeError("Kaboom!")
```

Run locally with Uvicorn (assuming you saved the above as `main.py`):

```sh
uvicorn main:app --reload
```

## Build

```sh
uv build
```

## Test

```sh
uv run pytest
```
