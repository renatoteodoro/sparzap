"""Test runner do Sparzap — isola a suíte da configuração de Celery da máquina."""

from django.test.runner import DiscoverRunner


class SparzapTestRunner(DiscoverRunner):
    """
    Força o modo eager do Celery durante os testes.

    Sem isto, rodar a suíte numa máquina com broker de verdade
    (`CELERY_TASK_ALWAYS_EAGER=False` no `.env`, que é o certo para testar o
    ritmo real de uma campanha) enfileira as tasks em vez de executá-las, e os
    testes que checam o efeito delas falham — o webhook não processa o evento,
    a campanha não dispara, o script não avança. A suíte tem que valer o mesmo
    em qualquer máquina, com ou sem worker rodando.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        from django.conf import settings

        from core.celery import app as celery_app

        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_EAGER_PROPAGATES = True
        # O app do Celery já leu a config no import; não basta mexer no settings.
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
