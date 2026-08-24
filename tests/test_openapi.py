from fastapi.testclient import TestClient


def test_openapi_documents_routes_security_and_upload_schema(
    client: TestClient,
) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Async Document Processing API"
    assert schema["info"]["version"] == "1.0.0"
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "description": "JWT access token returned by the login endpoint.",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    assert schema["paths"]["/documents/upload"]["post"]["requestBody"]
    assert schema["paths"]["/documents/{document_id}/process"]["post"]
    assert schema["paths"]["/jobs/{job_id}"]["get"]
    assert schema["paths"]["/search"]["get"]
    assert schema["paths"]["/auth/me"]["get"]["security"] == [
        {"HTTPBearer": []}
    ]
