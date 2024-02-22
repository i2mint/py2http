"""This module defines several type aliases and constants related to function parameters and signatures. 

The `WriteOpResult` TypedDict represents the result of a write operation, with keys for the success status (`ok`), number of items affected (`n`), and identifiers (`ids`) of the affected items.

The `ParameterKind` constant represents the type of a Parameter, specifically `Parameter.POSITIONAL_OR_KEYWORD`.

The `Params` alias is used to represent an Iterable of Parameter objects, while `HasParams` is a union type that can represent various structures that contain Parameter objects, such as Iterable, Mapping, Signature, or Callable.

Additionally, shorthand constants are defined for the different kinds of parameters: 
- `PK` for `Parameter.POSITIONAL_OR_KEYWORD`
- `VP` and `VK` for `Parameter.VAR_POSITIONAL` and `Parameter.VAR_KEYWORD` respectively
- `PO` and `KO` for `Parameter.POSITIONAL_ONLY` and `Parameter.KEYWORD_ONLY` respectively
- `var_param_kinds` is a set containing `VP` and `VK` for easy access to variable parameter kinds.

This module provides a convenient way to work with function parameters and signatures in Python."""
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
