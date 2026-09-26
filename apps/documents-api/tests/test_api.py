from documents_app.api import content_disposition, etag, parse_if_match


def test_etag_round_trip_and_unicode_download_filename() -> None:
    assert parse_if_match(etag(17)) == 17
    header = content_disposition("hotărâre ședință.txt")
    assert header.startswith('attachment; filename="hotarare sedinta.txt"')
    assert "filename*=UTF-8''hot%C4%83r%C3%A2re%20%C8%99edin%C8%9B%C4%83.txt" in header
