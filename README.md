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
import logging
from fastapi import Depends
from ds_fastapi import EnhancedFastAPI, UncaughtExceptionMiddleware

app = EnhancedFastAPI(debug=True)

# Add the middleware LAST so it can catch everything
app.add_middleware(
    UncaughtExceptionMiddleware,
    logger=logging.getLogger("uvicorn.error"),
    debug=app.debug,
)

# Optional: a dependency with documented error responses
def require_auth():
    # ... validate auth here, or raise HTTPException(status_code=401) ...
    return True

# Tell EnhancedFastAPI how to document dependency errors
require_auth.responses = {401: {"description": "Unauthorized"}}

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
