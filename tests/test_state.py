from pipeline.state import Pipeline_State

def test_fields():
    state: Pipeline_State = {
        "input_file": "/doc.pdf",
        "output_dir": "output",
        "error": None
    }
    assert state["error"] == None
    assert state["output_dir"] == "output"