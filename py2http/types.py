from inspect import Parameter, Signature
from typing import TypedDict, Optional, Iterable, Union, Mapping, Callable

WriteOpResult = TypedDict('WriteOpResult', ok=bool, n=int, ids=Iterable[str])
ParameterKind = type(Parameter.POSITIONAL_OR_KEYWORD)  # to get the enum type

Params = Iterable[Parameter]
HasParams = Union[Iterable[Parameter], Mapping[str, Parameter], Signature, Callable]

# short hands for Parameter kinds
PK = Parameter.POSITIONAL_OR_KEYWORD
VP, VK = Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD
PO, KO = Parameter.POSITIONAL_ONLY, Parameter.KEYWORD_ONLY
var_param_kinds = {VP, VK}
