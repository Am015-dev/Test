"""QA wrapper: the real app, with the GitHub gist replaced by an in-memory dict (a throwaway
profile must not be written to a real gist). Only shortlist._gh is stubbed."""
import json, os, runpy, sys
sys.path.insert(0, "/home/user/Test")
os.environ["GITHUB_TOKEN"] = "qa-local-not-a-token"
from scout import shortlist  # noqa: E402
_store = shortlist.__dict__.setdefault("_qa_store", {"content": "[]"})
def _gh(method, path, **kw):
    if method == "GET" and path.startswith("/gists?"):
        return [{"id": "fake", "description": shortlist.GIST_DESC, "files": {shortlist.GIST_FILE: {}}}]
    if method == "GET":
        return {"files": {shortlist.GIST_FILE: {"content": _store["content"]}}}
    if method == "PATCH":
        _store["content"] = kw["json"]["files"][shortlist.GIST_FILE]["content"]
        return {}
    return {}
shortlist._gh = _gh
runpy.run_path("/home/user/Test/src/scout/ui/app.py", run_name="__main__")
