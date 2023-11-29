import json
import logging
from enum import Enum
from typing import Generator, List, Optional

from pydantic import BaseModel, Field, confloat, conint
from llmstack.common.blocks.llm.localai import LocalAIChatCompletionsAPIProcessor, LocalAIChatCompletionsAPIProcessorConfiguration, LocalAIChatCompletionsAPIProcessorInput, LocalAIChatCompletionsAPIProcessorOutput
from llmstack.processors.providers.api_processor_interface import CHAT_WIDGET_NAME, ApiProcessorInterface, ApiProcessorSchema
from llmstack.common.blocks.llm.openai import FunctionCall as OpenAIFunctionCall, OpenAIAPIInputEnvironment

from asgiref.sync import async_to_sync


logger = logging.getLogger(__name__)


class Role(str, Enum):
    SYSTEM = 'system'
    USER = 'user'
    ASSISTANT = 'assistant'
    FUNCTION = 'function'

    def __str__(self):
        return self.value


class FunctionCallResponse(BaseModel):
    name: Optional[str]
    arguments: Optional[str]


class ChatMessage(BaseModel):
    role: Optional[Role] = Field(
        default=Role.USER, description="The role of the message sender. Can be 'user' or 'assistant' or 'system'.",
    )
    content: Optional[str] = Field(
        default='', description='The message text.', widget='textarea',
    )
    name: Optional[str] = Field(
        default='', widget='hidden',
        description='The name of the author of this message or the function name.',
    )
    function_call: Optional[FunctionCallResponse] = Field(
        widget='hidden',
        description='The name and arguments of a function that should be called, as generated by the model.',
    )


class FunctionCall(ApiProcessorSchema):
    name: str = Field(
        default='', description='The name of the function to be called. Must be a-z, A-Z, 0-9, or contain underscores and dashes, with a maximum length of 64.',
    )
    description: Optional[str] = Field(
        default=None, description='The description of what the function does.',
    )
    parameters: Optional[str] = Field(
        title='Parameters', widget='textarea',
        default=None, description='The parameters the functions accepts, described as a JSON Schema object. See the guide for examples, and the JSON Schema reference for documentation about the format.',
    )


class ChatCompletionInput(ApiProcessorSchema):
    system_message: Optional[str] = Field(
        default='', description='A message from the system, which will be prepended to the chat history.', widget='textarea',
    )
    messages: List[ChatMessage] = Field(
        default=[ChatMessage()], description='A list of messages, each with a role and message text.',
    )
    functions: Optional[List[FunctionCall]] = Field(
        default=None,
        description='A list of functions the model may generate JSON inputs for .',
    )


class ChatCompletionsOutput(ApiProcessorSchema):
    choices: List[ChatMessage] = Field(
        default=[], description='Messages', widget=CHAT_WIDGET_NAME,
    )
    _api_response: Optional[dict] = Field(
        default={}, description='Raw processor output.',
    )


class ChatCompletionsConfiguration(ApiProcessorSchema):
    base_url: Optional[str] = Field(description="Base URL")
    model: str = Field(description="Model name", widget='customselect', advanced_parameter=False,
                       options=['ggml-gpt4all-j'], default='ggml-gpt4all-j')
    max_tokens: Optional[conint(ge=1, le=32000)] = Field(
        1024,
        description='The maximum number of tokens allowed for the generated answer. By default, the number of tokens the model can return will be (4096 - prompt tokens).\n',
        example=1024,
    )
    temperature: Optional[confloat(ge=0.0, le=2.0, multiple_of=0.1)] = Field(
        default=0.7,
        description='What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic.\n\nWe generally recommend altering this or `top_p` but not both.\n',
        example=1,
        advanced_parameter=False,
    )
    stream: Optional[bool] = Field(
        default=False, description="Stream output", example=False)
    function_call: Optional[str] = Field(
        default=None,
        description='Controls how the model responds to function calls.',
    )


class ChatCompletions(ApiProcessorInterface[ChatCompletionInput, ChatCompletionsOutput, ChatCompletionsConfiguration]):
    @staticmethod
    def name() -> str:
        return 'Chat Completions'

    @staticmethod
    def slug() -> str:
        return 'chatgpt'

    @staticmethod
    def description() -> str:
        return 'Chat completions from LocalAI'

    @staticmethod
    def provider_slug() -> str:
        return 'localai'

    def process(self) -> dict:
        env = self._env
        base_url = env.get("localai_base_url")
        api_key = env.get("localai_api_key")

        if self._config.base_url:
            base_url = self._config.base_url

        if not base_url:
            raise Exception("Base URL is not set")

        system_message = self._input.system_message

        chat_messages = [
            {"role": "system", "content": system_message}] if system_message else []
        chat_messages.extend(
            json.loads(msg_entry.json()) for msg_entry in self._input.messages
        )
        openai_functions = None
        if self._input.functions is not None:
            openai_functions = [
                OpenAIFunctionCall(
                    name=function.name,
                    description=function.description,
                    parameters=json.loads(function.parameters)
                    if function.parameters is not None
                    else {},
                )
                for function in self._input.functions
            ]
        localai_chat_completions_api_processor_input = LocalAIChatCompletionsAPIProcessorInput(
            env=OpenAIAPIInputEnvironment(openai_api_key=api_key),
            system_message=system_message,
            chat_history=[],
            messages=self._input.messages,
            functions=openai_functions,
        )

        if self._config.stream:
            result_iter: Generator[LocalAIChatCompletionsAPIProcessorOutput, None, None] = LocalAIChatCompletionsAPIProcessor(
                configuration=LocalAIChatCompletionsAPIProcessorConfiguration(
                    base_url=base_url,
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                    stream=True,
                    function_call=self._config.function_call
                ).dict(),
            ).process_iter(localai_chat_completions_api_processor_input.dict())

            for result in result_iter:
                async_to_sync(self._output_stream.write)(
                    ChatCompletionsOutput(choices=result.choices))
        else:
            result: LocalAIChatCompletionsAPIProcessorOutput = LocalAIChatCompletionsAPIProcessor(
                configuration=LocalAIChatCompletionsAPIProcessorConfiguration(
                    base_url=base_url,
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                    stream=False,
                    function_call=self._config.function_call
                ).dict(),
            ).process(localai_chat_completions_api_processor_input.dict())

            async_to_sync(self._output_stream.write)(
                ChatCompletionsOutput(choices=result.choices))

        return self._output_stream.finalize()
