# pylint: disable=protected-access
# -*- coding: utf-8 -*-
# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

# try/except added for compatibility with python < 3.8
try:
    from unittest import mock
except ImportError:  # pragma: NO COVER
    import mock

import pytest
import glob

from google.cloud.documentai_toolbox import document

from google.cloud import documentai
from google.cloud.vision import AnnotateFileResponse


def get_bytes(file_name):
    result = []
    for filename in glob.glob(os.path.join(file_name, "*.json")):
        with open(os.path.join(os.getcwd(), filename), "rb") as f:
            result.append(f.read())

    return result


@pytest.fixture
def get_bytes_single_file_mock():
    with mock.patch.object(document, "_get_bytes") as byte_factory:
        byte_factory.return_value = get_bytes("tests/unit/resources/0")
        yield byte_factory


@pytest.fixture
def get_bytes_multiple_files_mock():
    with mock.patch.object(document, "_get_bytes") as byte_factory:
        byte_factory.return_value = get_bytes("tests/unit/resources/1")
        yield byte_factory


@pytest.fixture
def get_bytes_unordered_files_mock():
    with mock.patch.object(document, "_get_bytes") as byte_factory:
        byte_factory.return_value = get_bytes("tests/unit/resources/unordered_shards")
        yield byte_factory


@pytest.fixture
def get_bytes_form_parser_mock():
    with mock.patch.object(document, "_get_bytes") as byte_factory:
        byte_factory.return_value = get_bytes("tests/unit/resources/form_parser")
        yield byte_factory


@pytest.fixture
def get_bytes_splitter_mock():
    with mock.patch.object(document, "_get_bytes") as byte_factory:
        byte_factory.return_value = get_bytes("tests/unit/resources/splitter")
        yield byte_factory


def test_get_shards_with_gcs_uri_contains_file_type():
    with pytest.raises(ValueError, match="gcs_prefix cannot contain file types"):
        document._get_shards(
            gcs_bucket_name="test-directory",
            gcs_prefix="documentai/output/123456789/0.json",
        )


def test_get_shards_with_valid_gcs_uri(get_bytes_single_file_mock):
    actual = document._get_shards(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0/"
    )

    get_bytes_single_file_mock.assert_called_once()
    # We are testing only one of the fields to make sure the file content could be loaded.
    assert actual[0].pages[0].page_number == 1


def test_pages_from_shards():
    shards = []
    for byte in get_bytes("tests/unit/resources/0"):
        shards.append(documentai.Document.from_json(byte))

    actual = document._pages_from_shards(shards=shards)
    assert len(actual[0].paragraphs) == 31

    for page_index, page in enumerate(actual):
        assert page.documentai_page.page_number == page_index + 1


def test_entities_from_shard():
    shards = []
    for byte in get_bytes("tests/unit/resources/0"):
        shards.append(documentai.Document.from_json(byte))

    actual = document._entities_from_shards(shards=shards)

    assert actual[0].mention_text == "$140.00"
    assert actual[0].type_ == "vat"
    assert actual[1].mention_text == "$140.00"
    assert actual[1].type_ == "vat/tax_amount"
    assert actual[1].normalized_text == "140 USD"


def test_document_from_document_path_with_single_shard():
    actual = document.Document.from_document_path(
        document_path="tests/unit/resources/0/toolbox_invoice_test-0.json"
    )
    assert len(actual.pages) == 1


def test_document_from_documentai_document_with_single_shard():
    with open(
        "tests/unit/resources/0/toolbox_invoice_test-0.json", "r", encoding="utf-8"
    ) as f:
        doc = documentai.Document.from_json(f.read())

    actual = document.Document.from_documentai_document(documentai_document=doc)
    assert len(actual.pages) == 1


def test_document_from_gcs_with_single_shard(get_bytes_single_file_mock):
    actual = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0/"
    )

    get_bytes_single_file_mock.assert_called_once()
    assert len(actual.pages) == 1


def test_document_from_gcs_with_multiple_shards(get_bytes_multiple_files_mock):
    actual = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/1/"
    )
    get_bytes_multiple_files_mock.assert_called_once()

    assert len(actual.pages) == 48


def test_document_from_gcs_with_unordered_shards(get_bytes_unordered_files_mock):
    actual = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/2/"
    )
    get_bytes_unordered_files_mock.assert_called_once()

    expected_shard_count = len(actual.shards)
    current_text_offset = 0
    for expected_shard_index, shard in enumerate(actual.shards):
        assert int(shard.shard_info.shard_index) == expected_shard_index
        assert int(shard.shard_info.shard_count) == expected_shard_count
        assert int(shard.shard_info.text_offset) == current_text_offset
        current_text_offset += len(shard.text)

    for page_index, page in enumerate(actual.pages):
        assert page.documentai_page.page_number == page_index + 1


def test_search_page_with_target_string(get_bytes_single_file_mock):
    doc = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0/"
    )

    actual_string = doc.search_pages(target_string="contract")

    get_bytes_single_file_mock.assert_called_once()
    assert len(actual_string) == 1


def test_search_page_with_target_pattern(get_bytes_single_file_mock):
    doc = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0/"
    )

    actual_regex = doc.search_pages(pattern=r"\$\d+(?:\.\d+)?")

    get_bytes_single_file_mock.assert_called_once()
    assert len(actual_regex) == 1


def test_search_page_with_regex_and_str(get_bytes_single_file_mock):
    with pytest.raises(
        ValueError,
        match="Exactly one of target_string and pattern must be specified.",
    ):
        doc = document.Document.from_gcs(
            gcs_bucket_name="test-directory",
            gcs_prefix="documentai/output/123456789/0/",
        )
        doc.search_pages(pattern=r"^\$?(\d*(\d\.?|\.\d{1,2}))$", target_string="hello")

        get_bytes_single_file_mock.assert_called_once()


def test_search_page_with_none(get_bytes_single_file_mock):
    with pytest.raises(
        ValueError,
        match="Exactly one of target_string and pattern must be specified.",
    ):
        doc = document.Document.from_gcs(
            gcs_bucket_name="test-directory",
            gcs_prefix="documentai/output/123456789/0/",
        )
        doc.search_pages()

        get_bytes_single_file_mock.assert_called_once()


def test_get_entity_by_type(get_bytes_single_file_mock):
    doc = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0"
    )

    actual = doc.get_entity_by_type(target_type="receiver_address")

    get_bytes_single_file_mock.assert_called_once()

    assert len(actual) == 1
    assert actual[0].type_ == "receiver_address"
    assert actual[0].mention_text == "222 Main Street\nAnytown, USA"


@mock.patch("google.cloud.documentai_toolbox.wrappers.document.storage")
def test_get_bytes(mock_storage):
    client = mock_storage.Client.return_value
    mock_bucket = mock.Mock()
    client.Bucket.return_value = mock_bucket

    mock_ds_store = mock.Mock(name=[])
    mock_ds_store.name = "DS_Store"

    mock_blob1 = mock.Mock(name=[])
    mock_blob1.name = "gs://test-directory/1/test-annotations.json"
    mock_blob1.download_as_bytes.return_value = (
        "gs://test-directory/1/test-annotations.json"
    )

    mock_blob2 = mock.Mock(name=[])
    mock_blob2.name = "gs://test-directory/1/test-config.json"
    mock_blob2.download_as_bytes.return_value = "gs://test-directory/1/test-config.json"

    mock_blob3 = mock.Mock(name=[])
    mock_blob3.name = "gs://test-directory/1/test.pdf"
    mock_blob3.download_as_bytes.return_value = "gs://test-directory/1/test.pdf"

    client.list_blobs.return_value = [mock_ds_store, mock_blob1, mock_blob2, mock_blob3]

    actual = document._get_bytes(
        gcs_bucket_name="bucket",
        gcs_prefix="prefix",
    )

    assert actual == [
        "gs://test-directory/1/test-annotations.json",
        "gs://test-directory/1/test-config.json",
    ]


def test_get_form_field_by_name(get_bytes_form_parser_mock):
    doc = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0"
    )
    actual = doc.get_form_field_by_name(target_field="Phone #:")

    get_bytes_form_parser_mock.assert_called_once()

    assert len(actual) == 1
    assert actual[0].field_name == "Phone #:"
    assert actual[0].field_value == "(906) 917-3486"


def test_entities_to_dict(get_bytes_single_file_mock):
    doc = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0"
    )
    actual = doc.entities_to_dict()

    get_bytes_single_file_mock.assert_called_once()

    assert len(actual) == 25
    assert actual.get("vat") == "$140.00"
    assert actual.get("vat_tax_amount") == "$140.00"


@mock.patch("google.cloud.documentai_toolbox.wrappers.document.bigquery")
def test_entities_to_bigquery(mock_bigquery, get_bytes_single_file_mock):
    client = mock_bigquery.Client.return_value

    mock_table = mock.Mock()
    client.dataset.table.return_value = mock_table

    mock_load_job = mock.Mock()
    client.load_table_from_json.return_value = mock_load_job

    doc = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0"
    )

    actual = doc.entities_to_bigquery(
        dataset_name="test_dataset", table_name="test_table", project_id="test_project"
    )

    get_bytes_single_file_mock.assert_called_once()
    mock_bigquery.Client.assert_called_once()

    assert actual


@mock.patch("google.cloud.documentai_toolbox.wrappers.document.Pdf")
def test_split_pdf(mock_Pdf, get_bytes_splitter_mock):
    doc = document.Document.from_gcs(
        gcs_bucket_name="test-directory", gcs_prefix="documentai/output/123456789/0"
    )
    mock_input_file = mock.Mock()
    mock_Pdf.open.return_value.__enter__.return_value.name = mock_input_file

    mock_output_file = mock.Mock()
    mock_Pdf.new.return_value = mock_output_file

    actual = doc.split_pdf(
        pdf_path="procurement_multi_document.pdf", output_path="splitter/output/"
    )

    get_bytes_splitter_mock.assert_called_once()

    assert actual == [
        "procurement_multi_document_pg1_invoice_statement.pdf",
        "procurement_multi_document_pg2_receipt_statement.pdf",
        "procurement_multi_document_pg3_other.pdf",
        "procurement_multi_document_pg4_utility_statement.pdf",
        "procurement_multi_document_pg5_restaurant_statement.pdf",
        "procurement_multi_document_pg6-7_other.pdf",
    ]


def test_convert_document_to_annotate_file_response():
    doc = document.Document.from_document_path(
        document_path="tests/unit/resources/0/toolbox_invoice_test-0.json"
    )

    actual = doc.convert_document_to_annotate_file_response()

    assert actual != AnnotateFileResponse()
