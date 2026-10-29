import unittest

from ops.public_probe import MAX_LATENCY_MS, evaluate, public_url


def corpo(status="ok", schema="compatible"):
    return {"status": status, "schema": schema}


class PublicProbeTests(unittest.TestCase):
    def test_dominio_saudavel_passa_com_acao_em_cada_sonda(self):
        report = evaluate(200, corpo(), "nginx", 120)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(all(item["action"] for item in report["probes"]))

    def test_cada_sonda_pode_reprovar_sozinha(self):
        casos = {
            "status": (503, corpo(), "nginx", 120),
            "payload": (200, corpo(schema="incompatible"), "nginx", 120),
            "versao-na-borda": (200, corpo(), "nginx/1.30.6", 120),
            "latencia": (200, corpo(), "nginx", MAX_LATENCY_MS + 1),
        }
        for nome, argumentos in casos.items():
            with self.subTest(nome=nome):
                self.assertEqual(evaluate(*argumentos)["status"], "critical")

    def test_resposta_sem_json_nao_passa_por_saudavel(self):
        self.assertEqual(evaluate(200, {}, "nginx", 10)["status"], "critical")

    def test_url_exige_https_e_recusa_credencial(self):
        self.assertEqual(
            public_url("https://aulas.exemplo.test"), "https://aulas.exemplo.test/api/health"
        )
        for invalida in (
            "http://aulas.exemplo.test",
            "https://u:s@aulas.exemplo.test",
            "https://aulas.exemplo.test?debug=1",
            "https://aulas.exemplo.test#frag",
            "ftp://aulas.exemplo.test",
            "aulas.exemplo.test",
        ):
            with self.subTest(url=invalida), self.assertRaises(ValueError):
                public_url(invalida)

    def test_relatorio_nao_carrega_url_nem_corpo(self):
        report = evaluate(
            200, {"status": "ok", "schema": "compatible", "extra": "segredo"}, "nginx", 10
        )
        texto = repr(report)
        self.assertNotIn("segredo", texto)
        self.assertNotIn("aulas.exemplo.test", texto)

    def test_detalhes_internos_no_health_publico_reprovam_sem_refletir_valores(self):
        for field in ("version", "env", "schema_current", "schema_required"):
            with self.subTest(field=field):
                report = evaluate(200, {**corpo(), field: "private-value"}, "nginx", 10)
                self.assertEqual(report["status"], "critical")
                self.assertNotIn("private-value", repr(report))
