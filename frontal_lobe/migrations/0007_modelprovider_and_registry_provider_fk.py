from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('frontal_lobe', '0006_alter_reasoningturn_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModelProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('key', models.CharField(help_text='Stable identifier, e.g. "ollama", "openrouter", "local".', max_length=50, unique=True)),
                ('base_url', models.URLField(help_text='Base URL for this provider, e.g. https://openrouter.ai/api', max_length=255)),
                ('chat_path', models.CharField(default='/v1/chat/completions', help_text='Path segment for chat completions, appended to base_url.', max_length=255)),
                ('requires_api_key', models.BooleanField(default=False, help_text='Whether this provider requires an API key for requests.')),
                ('api_key_header', models.CharField(default='Authorization', help_text='Header name used to send the API key (e.g. Authorization).', max_length=100)),
                ('api_key_env_var', models.CharField(blank=True, help_text='Environment variable name that stores the API key.', max_length=100, null=True)),
            ],
            options={
                'verbose_name_plural': 'Model Providers',
            },
        ),
        migrations.AddField(
            model_name='modelregistry',
            name='provider',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='models', to='frontal_lobe.modelprovider'),
        ),
    ]

