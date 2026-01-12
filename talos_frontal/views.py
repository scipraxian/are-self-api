import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from talos_frontal.models import SystemDirective
from talos_frontal.utils import parse_ai_actions
from talos_parietal.registry import ModelRegistry
from talos_parietal.synapse import OllamaClient
from talos_parietal.tools import ai_execute_task, ai_read_file, ai_search_file

logger = logging.getLogger(__name__)


class ChatOverrideView(View):
    """
    MANUAL OVERRIDE: Directly chat with the Frontal Lobe.
    """

    def post(self, request, *args, **kwargs):
        message = request.POST.get('message', '')
        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        # 1. Load active SystemDirective (Manual Override - ID 2)
        directive = SystemDirective.objects.filter(
            identifier_id=SystemDirective.MANUAL_OVERRIDE_ID,
            is_active=True).order_by('-version').first()

        if not directive:
            return JsonResponse({'error': 'No active Manual Override Directive found (ID 2)'}, status=500)

        # 2. Prepare Context
        context = {
            'project_root': str(settings.BASE_DIR),  # Default to Talos root
        }

        try:
            system_prompt = directive.format_prompt(**context)
        except KeyError as e:
            logger.error(f"Failed to format system prompt: {e}")
            system_prompt = directive.template

        # 3. Inject into OllamaClient
        model_name = ModelRegistry.get_model('scout_light')
        client = OllamaClient(model=model_name)

        options = {
            'temperature': directive.temperature,
            'num_ctx': directive.context_window_size,
            'num_predict': directive.max_output_tokens,
        }

        response_data = client.chat(
            system_prompt=system_prompt,
            user_content=message,
            options=options
        )

        content = response_data.get('content', '')

        # 4. TOOL EXECUTION LAYER
        actions = parse_ai_actions(content)

        if actions:
            tool_output = "\n\n--- MANUAL TOOL EXECUTION ---\n"
            for action in actions:
                tool_name = action.get('tool')
                args = action.get('args', {})

                # Safety Injection
                if tool_name in ['ai_read_file', 'ai_search_file']:
                    args['root_path'] = context['project_root']

                if tool_name == 'ai_read_file':
                    res = ai_read_file(
                        args.get('path'),
                        root_path=args.get('root_path'),
                        start_line=args.get('start_line', 1),
                        max_lines=min(int(args.get('max_lines', 50)), 150)
                    )
                elif tool_name == 'ai_search_file':
                    res = ai_search_file(args.get('path'), args.get('pattern'), root_path=args.get('root_path'))
                elif tool_name == 'ai_execute_task':
                    res = ai_execute_task(args.get('head_id'))
                else:
                    res = f"Error: Unknown tool '{tool_name}'"

                tool_output += f"> {tool_name}: \n{res}\n"

            content += tool_output

        return JsonResponse({
            'response': content,
            'tokens_input': response_data.get('tokens_input', 0),
            'tokens_output': response_data.get('tokens_output', 0),
            'model': response_data.get('model', model_name)
        })

    def get(self, request, *args, **kwargs):
        return render(request, 'dashboard/partials/chat_window.html')
