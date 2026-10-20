# py2http.sizeof

Approximate the memory an object holds, without walking more of it than a budget.

`bounded_deep_sizeof` is how py2http bounds the objects clients create or grow
through class and instance endpoints (`py2http.obj_dispatch`).

### Functions

| [`bounded_deep_sizeof`](#py2http.sizeof.bounded_deep_sizeof)(obj[, limit])   | Approximate memory held by `obj` and everything it references (containers, instance `__dict__` and `__slots__`, what a bound method, a `partial` or a function's closure, attributes and defaults hold), counting each object once.   |
|--------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### py2http.sizeof.bounded_deep_sizeof(obj, limit=None)

Approximate memory held by `obj` and everything it references (containers,
instance `__dict__` and `__slots__`, what a bound method, a `partial` or a
function’s closure, attributes and defaults hold), counting each object once. Stops
as soon as the total exceeds `limit`, so measuring costs at most about `limit`
bytes’ worth of objects. Classes, modules and the code of functions are shared, so
not counted, and neither is what classes and modules hold (class attributes, module
globals), nor caches kept in C (`lru_cache`). Holding a bound method of another
object counts that whole object, as holding the object itself would.

```pycon
>>> small, big = bounded_deep_sizeof([1, 2]), bounded_deep_sizeof(list(range(1000)))
>>> small < big
True
>>> bounded_deep_sizeof(list(range(10**6)), limit=1000) > 1000
True
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
