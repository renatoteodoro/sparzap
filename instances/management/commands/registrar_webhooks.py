from django.conf import settings
from django.core.management.base import BaseCommand

from instances.evolution import EVOLUTION_WEBHOOK_EVENTS, EvolutionClient, EvolutionError
from instances.models import Instance


class Command(BaseCommand):
    help = (
        'Reescreve na Evolution o webhook de todas as instâncias, usando a '
        'EVOLUTION_WEBHOOK_BASE_URL atual. Rode sempre que o endereço do '
        'Sparzap mudar (dev <-> produção, domínio novo na VPS) — sem isso a '
        'Evolution continua chamando o endereço antigo e as respostas somem '
        'sem erro nenhum.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Só mostra as URLs que seriam registradas, sem chamar a Evolution.',
        )

    def handle(self, *args, **options):
        base_url = settings.EVOLUTION_WEBHOOK_BASE_URL
        dry_run = options['dry_run']
        client = EvolutionClient()

        instancias = Instance.objects.all()
        if not instancias:
            self.stdout.write('Nenhuma instância cadastrada.')
            return

        self.stdout.write(f'URL base: {base_url}')
        falhas = 0
        for instancia in instancias:
            nome = instancia.evolution_instance_name
            url = f'{base_url}/webhooks/evolution/{nome}/?token={settings.EVOLUTION_WEBHOOK_SECRET}'

            if dry_run:
                self.stdout.write(f'  [dry-run] {nome} -> {url.split("?")[0]}')
                continue

            try:
                client.set_webhook(nome, url, EVOLUTION_WEBHOOK_EVENTS)
            except EvolutionError as exc:
                # Uma instância fora do ar não pode impedir o registro das outras.
                falhas += 1
                self.stderr.write(self.style.ERROR(f'  falhou {nome}: {exc}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'  ok {nome} -> {url.split("?")[0]}'))

        if falhas:
            self.stdout.write(f'{falhas} instância(s) falharam.')
