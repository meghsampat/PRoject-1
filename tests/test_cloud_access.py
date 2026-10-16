"""Cloud preparation tests use stubs; they never demonstrate actual provider access."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from src.cloud_access import cloud_configuration,preflight,perform_smoke


class CloudTests(unittest.TestCase):
    def setUp(self):
        # Historical provider contracts are tested only with injected stubs.
        self.enterContext(patch("src.config.LOCAL_ONLY_MODE", False))

    def test_project_identity_not_inferred_or_placeholder_accepted(self):
        with patch.dict("os.environ",{},clear=True):
            self.assertIsNone(cloud_configuration()["project_id"])
        for project in ["your-project-id","<PROJECT_ID>","NOT_VALID","not-created"]:
            with self.assertRaises(ValueError):cloud_configuration(project=project)

    def test_preflight_does_not_claim_access_from_local_presence(self):
        with patch("src.cloud_access.sdk_version",return_value="2.30.0"),patch("src.cloud_access.credential_hint",return_value="local_application_default_credentials"),patch.dict("os.environ",{},clear=True):
            result=preflight(cloud_configuration(project="fmcg-demo-123"))
        self.assertEqual(result["status"],"READY_TO_ATTEMPT")
        self.assertFalse(result["cloud_call_verified"])
        self.assertFalse(result["billing_verified"])

    def test_stub_call_uses_cloud_credentials_fixed_prompt_and_closes_client(self):
        client=Mock()
        client.models.generate_content.return_value=SimpleNamespace(text="Hello")
        factory=Mock(return_value=client)
        credentials=object()
        result=perform_smoke(cloud_configuration(project="fmcg-demo-123"),factory,Mock(return_value=(credentials,None)))
        self.assertTrue(result["cloud_call_verified"])
        self.assertIs(factory.call_args.kwargs["credentials"],credentials)
        self.assertTrue(factory.call_args.kwargs["enterprise"])
        self.assertNotIn("api_key",factory.call_args.kwargs)
        client.close.assert_called_once()

    def test_empty_text_is_not_pass_and_failed_calls_close_client(self):
        client=Mock()
        client.models.generate_content.return_value=SimpleNamespace(text=None)
        settings=cloud_configuration(project="fmcg-demo-123")
        result=perform_smoke(settings,Mock(return_value=client),Mock(return_value=(object(),None)))
        self.assertFalse(result["cloud_call_verified"])
        client.models.generate_content.side_effect=RuntimeError("stub")
        with self.assertRaises(RuntimeError):perform_smoke(settings,Mock(return_value=client),Mock(return_value=(object(),None)))
        self.assertEqual(client.close.call_count,2)


if __name__=="__main__":unittest.main()
