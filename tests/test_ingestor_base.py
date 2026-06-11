import pytest

from pydantic import ValidationError

from ingestor.base import TextChunk

def test_check_testchunk_immutable():
    result = TextChunk(chunk_id=1, text="test")
    with pytest.raises(ValidationError):
        result.text = "new_test"
        
    