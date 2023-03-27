"""Wrapper around StochasticAI APIs."""
import logging
import time
from typing import Any, Dict, List, Mapping, Optional

import requests
from pydantic import BaseModel, Extra, Field, root_validator

from langchain.llms.base import LLM
from langchain.llms.utils import enforce_stop_tokens
from langchain.schema import EnvAuthStrategy
from langchain.utils import get_from_dict_or_env

logger = logging.getLogger(__name__)


class StochasticAuthStrategy(EnvAuthStrategy):
    name = "STOCHASTICAI_API_KEY"


class StochasticAI(LLM, BaseModel):
    """Wrapper around StochasticAI large language models.

    To use, you should have the environment variable ``STOCHASTICAI_API_KEY``
    set with your API key.

    Example:
        .. code-block:: python

            from langchain.llms import StochasticAI
            api_url = "https://api-dev.stochastic.ai/v1/modelApi/submit/flan-t5"
            stochasticai = StochasticAI(model_id=api_url)
    """

    id = "stochasticai"
    """Unique ID for this provider class."""

    model_id: str
    """
    Model ID to invoke by this provider via generate/agenerate.
    For StochasticAI, this is the API URL to the model. 
    """

    models = ["*"]
    """List of supported models by their IDs. For registry providers, this will
    be just ["*"]."""

    pypi_package_deps = []
    """List of PyPi package dependencies."""

    auth_strategy = StochasticAuthStrategy
    """Authentication/authorization strategy. Declares what credentials are
    required to use this model provider. Generally should not be `None`."""

    model_kwargs: Dict[str, Any] = Field(default_factory=dict)
    """Holds any model parameters valid for `create` call not
    explicitly specified."""

    stochasticai_api_key: Optional[str] = None

    class Config:
        """Configuration for this pydantic object."""

        extra = Extra.forbid

    @root_validator(pre=True)
    def build_extra(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Build extra kwargs from additional params that were passed in."""
        all_required_field_names = {field.alias for field in cls.__fields__.values()}

        extra = values.get("model_kwargs", {})
        for field_name in list(values):
            if field_name not in all_required_field_names:
                if field_name in extra:
                    raise ValueError(f"Found {field_name} supplied twice.")
                logger.warning(
                    f"""{field_name} was transfered to model_kwargs.
                    Please confirm that {field_name} is what you intended."""
                )
                extra[field_name] = values.pop(field_name)
        values["model_kwargs"] = extra
        return values

    @root_validator()
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that api key exists in environment."""
        stochasticai_api_key = get_from_dict_or_env(
            values, "stochasticai_api_key", "STOCHASTICAI_API_KEY"
        )
        values["stochasticai_api_key"] = stochasticai_api_key
        return values

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters."""
        return {
            **{"model_id": self.model_id},
            **{"model_kwargs": self.model_kwargs},
        }

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """Call out to StochasticAI's complete endpoint.

        Args:
            prompt: The prompt to pass into the model.
            stop: Optional list of stop words to use when generating.

        Returns:
            The string generated by the model.

        Example:
            .. code-block:: python

                response = StochasticAI("Tell me a joke.")
        """
        params = self.model_kwargs or {}
        response_post = requests.post(
            url=self.model_id,
            json={"prompt": prompt, "params": params},
            headers={
                "apiKey": f"{self.stochasticai_api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        response_post.raise_for_status()
        response_post_json = response_post.json()
        completed = False
        while not completed:
            response_get = requests.get(
                url=response_post_json["data"]["responseUrl"],
                headers={
                    "apiKey": f"{self.stochasticai_api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response_get.raise_for_status()
            response_get_json = response_get.json()["data"]
            text = response_get_json.get("completion")
            completed = text is not None
            time.sleep(0.5)
        text = text[0]
        if stop is not None:
            # I believe this is required since the stop tokens
            # are not enforced by the model parameters
            text = enforce_stop_tokens(text, stop)
        return text
