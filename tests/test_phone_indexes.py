from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.firestore_repository import FirestoreRepository
from backend.models import Lead
from backend.phones import normalize_phone


def test_new_lead_document_contains_normalized_phone_indexes():
    repository = object.__new__(FirestoreRepository)
    lead = Lead(
        date="25/11/2026",
        company_name="Empresa QA",
        phone="(61) 99999-9999",
        cnpj_phone="(61) 3333-4444",
        place_id="place-qa",
    )

    document = repository._document(lead)

    assert document["phone_digits"] == "5561999999999"
    assert document["cnpj_phone_digits"] == "556133334444"


def test_phone_normalization_accepts_whatsapp_and_international_formats():
    assert normalize_phone("(61) 99999-9999") == "5561999999999"
    assert normalize_phone("0055 61 99999-9999") == "5561999999999"
    assert normalize_phone("5561999999999@s.whatsapp.net") == "5561999999999"


def test_backfill_only_updates_index_fields_and_sets_completion_marker():
    repository = object.__new__(FirestoreRepository)
    marker = MagicMock()
    marker.get.return_value = SimpleNamespace(exists=False)
    repository.migrations = MagicMock()
    repository.migrations.document.return_value = marker

    active = MagicMock()
    active.reference = MagicMock()
    active.to_dict.return_value = {
        "phone": "(61) 99999-9999",
        "cnpj_phone": "(61) 3333-4444",
    }
    archived = MagicMock()
    archived.reference = MagicMock()
    archived.to_dict.return_value = {"phone": "(62) 98888-7777"}
    repository.collection = MagicMock()
    repository.collection.stream.return_value = [active]
    repository.blocklist = MagicMock()
    repository.blocklist.stream.return_value = [archived]

    active_batch = MagicMock()
    archived_batch = MagicMock()
    client = MagicMock()
    client.batch.side_effect = [active_batch, archived_batch]

    with patch("backend.firestore_repository.firestore.client", return_value=client):
        updated = repository.backfill_phone_indexes()

    assert updated == 2
    active_batch.update.assert_called_once_with(active.reference, {
        "phone_digits": "5561999999999",
        "cnpj_phone_digits": "556133334444",
    })
    archived_batch.update.assert_called_once_with(archived.reference, {
        "phone_digits": "5562988887777",
    })
    active_batch.delete.assert_not_called()
    archived_batch.delete.assert_not_called()
    marker.set.assert_called_once()


def test_completed_backfill_does_not_scan_again():
    repository = object.__new__(FirestoreRepository)
    marker = MagicMock()
    marker.get.return_value = SimpleNamespace(exists=True)
    repository.migrations = MagicMock()
    repository.migrations.document.return_value = marker
    repository.collection = MagicMock()
    repository.blocklist = MagicMock()

    assert repository.backfill_phone_indexes() == 0
    repository.collection.stream.assert_not_called()
    repository.blocklist.stream.assert_not_called()
