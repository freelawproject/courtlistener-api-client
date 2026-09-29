"""String-typed endpoint fields accept numbers and send them as strings."""

import pytest
from pydantic import ValidationError

from courtlistener import CourtListener
from courtlistener.models import ENDPOINTS


def _params(resource, **filters):
    client = CourtListener(api_token="unused")
    return getattr(client, resource).validate_filters(filters)


class TestNumberToStringCoercion:
    def test_int_document_number(self):
        model = ENDPOINTS["recap_documents"](document_number=1)
        assert model.document_number == "1"

    def test_int_document_number_params(self):
        params = _params("recap_documents", document_number=1)
        assert params == {"document_number": "1"}

    def test_int_docket_number(self):
        params = _params("dockets", docket_number=123)
        assert params == {"docket_number": "123"}

    def test_int_search_query(self):
        assert _params("search", q=1983)["q"] == "1983"

    def test_int_in_filter_on_string_field(self):
        model = ENDPOINTS["recap_documents"](pacer_doc_id=[1, 2])
        assert model.pacer_doc_id == {"in": "1,2"}

    def test_int_lookup_stays_int(self):
        params = _params("recap_documents", document_number={"gte": "1"})
        assert params == {"document_number__gte": 1}

    def test_int_field_stays_int(self):
        assert _params("recap_documents", id=5) == {"id": 5}

    def test_int_choice_stays_int(self):
        assert _params("recap_documents", document_type=1) == {
            "document_type": 1
        }

    def test_bool_not_coerced(self):
        with pytest.raises(ValidationError):
            ENDPOINTS["recap_documents"](document_number=True)
