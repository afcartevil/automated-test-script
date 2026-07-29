from abc import ABC, abstractmethod
from typing import Any, Dict, Callable, TypeVar, Generic, Optional
import inspect
from functools import wraps

T = TypeVar('T')

class Depends(Generic[T]):
    """"""
    def __init__(self, dependency: Callable[..., T]):
        self.dependency = dependency
    
    def __call__(self, *args, **kwargs) -> T:
        return self.dependency(*args, **kwargs)
    
    def __repr__(self) -> str:
        return f"Depends({self.dependency.__name__})"


class DependencyResolver:
    """依赖解析器"""
    
    def __init__(self):
        self._providers: Dict[str, Callable] = {}
    
    def register_provider(self, name: str, provider: Callable):
        """注册依赖提供者"""
        self._providers[name] = provider
    
    def resolve_dependencies(self, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """解析函数的依赖"""
        sig = inspect.signature(func)
        resolved_deps = {}
        
        for param_name, param in sig.parameters.items():
            if isinstance(param.default, Depends):
                depends = param.default
                
                # 直接解析依赖，不使用缓存
                try:
                    resolved_value = self._resolve_dependency(depends)
                    resolved_deps[param_name] = resolved_value
                except Exception as e:
                    # 增加错误处理
                    raise ValueError(f"无法解析依赖 {param_name}: {e}") from e
        
        return resolved_deps
    
    def _resolve_dependency(self, depends: Depends) -> Any:
        """解析单个依赖"""
        try:
            # 检查依赖函数是否也有依赖
            dependency_deps = self.resolve_dependencies(depends.dependency)
            return depends.dependency(**dependency_deps)
        except Exception as e:
            raise ValueError(f"解析依赖 {depends.dependency.__name__} 失败: {e}") from e
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息（用于调试）"""
        return {
            "providers_count": len(self._providers)
        }


# 全局依赖解析器实例
_global_resolver = DependencyResolver()

def resolve(**dependencies) -> Dict[str, Any]:
    """参数调用方式的依赖解析函数
    
   支持以下形式：
    deps = resolve(
        platform_info=Depends(create_platform_info_provider(sn))
    )
    Args:
        **dependencies: 依赖声明字典
    Returns:
        Dict[str, Any]: 解析后的依赖实例字典
    """
    resolved = {}
    
    for name, depends in dependencies.items():
        if isinstance(depends, Depends):
            try:
                # 直接解析依赖，不使用缓存
                resolved_value = _global_resolver._resolve_dependency(depends)
                resolved[name] = resolved_value
            except Exception as e:
                raise ValueError(f"解析依赖 {name} 失败: {e}") from e
        else:
            # 直接传入的值
            resolved[name] = depends
    
    return resolved


def inject_dependencies(func: Callable) -> Callable:
    """依赖注入装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # 解析依赖
            deps = _global_resolver.resolve_dependencies(func, *args, **kwargs)
            # 合并到kwargs中
            kwargs.update(deps)
            return func(*args, **kwargs)
        except Exception as e:
            raise ValueError(f"依赖注入失败 in {func.__name__}: {e}") from e
    
    return wrapper


def get_dependency_stats() -> Dict[str, int]:
    """获取依赖系统统计信息（用于调试和监控）"""
    return _global_resolver.get_stats()