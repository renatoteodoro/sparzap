import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from instances.evolution import EvolutionRateLimited
from instances.models import Instance

from . import services
from .models import BlockEvent, DailyLimit, RateSettings, WarmupPlan


class CanSendTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='a@a.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            status=Instance.STATUS_CONECTADO,
            limite_diario=3,
            janela_inicio=datetime.time(0, 0),
            janela_fim=datetime.time(23, 59),
        )

    def test_bloqueia_se_instancia_inativa(self):
        self.instance.ativo = False
        self.instance.save()
        permitido, motivo, _ = services.can_send(self.instance)
        self.assertFalse(permitido)
        self.assertEqual(motivo, BlockEvent.MOTIVO_DESCONECTADO)

    def test_bloqueia_se_nao_conectado(self):
        self.instance.status = Instance.STATUS_DESCONECTADO
        self.instance.save()
        permitido, motivo, _ = services.can_send(self.instance)
        self.assertFalse(permitido)

    def test_bloqueia_fora_da_janela(self):
        # a versao anterior usava a janela 01:00-02:00 e o horario real do
        # relogio: entre 1h e 2h da manha o proprio teste caia DENTRO da
        # janela e falhava. Fixamos o "agora" para o teste ser deterministico
        # a qualquer hora do dia (ver docs/testes.md).
        self.instance.janela_inicio = datetime.time(8, 0)
        self.instance.janela_fim = datetime.time(21, 0)
        self.instance.save()

        # o check de janela acontece antes do de limite diario, entao o
        # localtime falso nao chega a afetar localdate()/DailyLimit
        with patch('django.utils.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = datetime.datetime(2026, 1, 1, 3, 0)
            permitido, motivo, _ = services.can_send(self.instance)

        self.assertFalse(permitido)
        self.assertEqual(motivo, BlockEvent.MOTIVO_FORA_JANELA)

    def test_permite_dentro_da_janela(self):
        self.instance.janela_inicio = datetime.time(8, 0)
        self.instance.janela_fim = datetime.time(21, 0)
        self.instance.save()

        with patch('django.utils.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = datetime.datetime(2026, 1, 1, 12, 0)
            permitido, motivo, _ = services.can_send(self.instance)

        self.assertTrue(permitido)
        self.assertIsNone(motivo)

    def test_bloqueia_ao_atingir_limite_diario(self):
        DailyLimit.objects.create(instance=self.instance, data=timezone.localdate(), enviadas=3)
        permitido, motivo, _ = services.can_send(self.instance)
        self.assertFalse(permitido)
        self.assertEqual(motivo, BlockEvent.MOTIVO_LIMITE_DIARIO)

    def test_permite_dentro_do_limite(self):
        DailyLimit.objects.create(instance=self.instance, data=timezone.localdate(), enviadas=1)
        permitido, motivo, _ = services.can_send(self.instance)
        self.assertTrue(permitido)
        self.assertIsNone(motivo)


class DispatchTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='b@b.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            status=Instance.STATUS_CONECTADO,
            limite_diario=10,
            # janela cobrindo o dia inteiro: este teste nao e' sobre janela,
            # nao pode depender do horario real em que roda (ver Sprint 7/17)
            janela_inicio=datetime.time(0, 0),
            janela_fim=datetime.time(23, 59),
        )

    def test_dispatch_bloqueado_levanta_antiblockblocked(self):
        self.instance.ativo = False
        self.instance.save()
        with self.assertRaises(services.AntiBlockBlocked):
            services.dispatch(self.instance, '+5511987654321', 'oi')

    @patch('instances.evolution.EvolutionClient.send_text')
    def test_dispatch_sucesso_incrementa_contador_e_registra_sucesso(self, mock_send):
        mock_send.return_value = {'key': {'id': 'ABC'}}
        rate = RateSettings.objects.create(instance=self.instance, falhas_consecutivas=2, fator_escalonamento=2.25)

        services.dispatch(self.instance, '+5511987654321', 'oi')

        limite = DailyLimit.objects.get(instance=self.instance, data=timezone.localdate())
        self.assertEqual(limite.enviadas, 1)
        rate.refresh_from_db()
        self.assertEqual(rate.falhas_consecutivas, 0)
        self.assertEqual(rate.fator_escalonamento, 1.0)

    @patch('instances.evolution.EvolutionClient.send_text')
    def test_dispatch_rate_limited_registra_falha_e_repropaga(self, mock_send):
        mock_send.side_effect = EvolutionRateLimited('429')
        with self.assertRaises(EvolutionRateLimited):
            services.dispatch(self.instance, '+5511987654321', 'oi')

        rate = RateSettings.objects.get(instance=self.instance)
        self.assertEqual(rate.falhas_consecutivas, 1)
        self.assertTrue(BlockEvent.objects.filter(instance=self.instance, motivo=BlockEvent.MOTIVO_RATE_LIMIT).exists())

    @patch('instances.evolution.EvolutionClient.send_text')
    def test_falhas_consecutivas_pausam_a_instancia_automaticamente(self, mock_send):
        mock_send.side_effect = EvolutionRateLimited('429')
        for _ in range(services.FALHAS_PARA_AUTO_PAUSA):
            with self.assertRaises(EvolutionRateLimited):
                services.dispatch(self.instance, '+5511987654321', 'oi')

        self.instance.refresh_from_db()
        self.assertFalse(self.instance.ativo)
        self.assertTrue(BlockEvent.objects.filter(instance=self.instance, pausou_instancia=True).exists())

    def test_next_delay_respeita_intervalo_configurado(self):
        RateSettings.objects.create(instance=self.instance, intervalo_min_s=10, intervalo_max_s=10)
        self.assertEqual(services.next_delay_seconds(self.instance), 10)


class WarmupTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='w@w.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            limite_diario=30,
        )

    def test_curva_comeca_em_5_e_termina_no_limite_final(self):
        self.assertEqual(services._curva_do_dia(1, 14, 30), 5)
        self.assertEqual(services._curva_do_dia(14, 14, 30), 30)
        # dia intermediario cresce monotonicamente
        self.assertLess(services._curva_do_dia(5, 14, 30), services._curva_do_dia(10, 14, 30))

    def test_start_warmup_guarda_limite_original_e_aplica_o_do_dia_1(self):
        plan = services.start_warmup(self.instance, dias_total=14)
        self.assertEqual(plan.limite_final, 30)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.limite_diario, 5)

    def test_advance_all_warmups_avanca_o_dia_e_ajusta_o_limite(self):
        plan = services.start_warmup(self.instance, dias_total=14)
        services.advance_all_warmups()
        plan.refresh_from_db()
        self.instance.refresh_from_db()
        self.assertEqual(plan.dia_atual, 2)
        self.assertGreater(self.instance.limite_diario, 5)

    def test_advance_apos_ultimo_dia_conclui_e_restaura_limite_final(self):
        plan = services.start_warmup(self.instance, dias_total=3)
        services.advance_all_warmups()  # dia 2
        services.advance_all_warmups()  # dia 3
        services.advance_all_warmups()  # passa do total -> conclui
        plan.refresh_from_db()
        self.instance.refresh_from_db()
        self.assertEqual(plan.status, WarmupPlan.STATUS_CONCLUIDO)
        self.assertEqual(self.instance.limite_diario, 30)

    def test_plano_pausado_nao_avanca(self):
        plan = services.start_warmup(self.instance, dias_total=14)
        services.pause_warmup(plan)
        services.advance_all_warmups()
        plan.refresh_from_db()
        self.assertEqual(plan.dia_atual, 1)
