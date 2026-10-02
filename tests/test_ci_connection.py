"""CI connects with key-pair settings from the environment; local runs are unchanged."""

import unittest

from quakewatch.raw_load import CI_ENV, LoadReconciliationError, env_connection_params


class EnvConnectionTest(unittest.TestCase):
    full = {
        CI_ENV["account"]: "acct",
        CI_ENV["user"]: "ci_user",
        CI_ENV["private_key_file"]: "/tmp/key.p8",
        CI_ENV["passphrase"]: "x",
    }

    def test_unset_environment_falls_back_to_local_profile(self):
        self.assertIsNone(env_connection_params({}))

    def test_full_environment_uses_project_role_and_key_pair(self):
        params = env_connection_params(self.full)
        self.assertEqual(params["role"], "QUAKEWATCH_ROLE")
        self.assertEqual(params["authenticator"], "SNOWFLAKE_JWT")
        self.assertEqual(params["warehouse"], "QUAKEWATCH_WH")
        self.assertEqual(params["private_key_file"], "/tmp/key.p8")

    def test_partial_environment_is_rejected_without_leaking_values(self):
        partial = dict(self.full)
        del partial[CI_ENV["passphrase"]]
        with self.assertRaises(LoadReconciliationError) as error:
            env_connection_params(partial)
        self.assertIn(CI_ENV["passphrase"], str(error.exception))
        self.assertNotIn("acct", str(error.exception))


if __name__ == "__main__":
    unittest.main()
