#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAHP EvoSkill 进化管理器 (run_evolution.py)

功能: 控制Skill的迭代优化循环
来源: TAHP-评估与质量门禁规范 §6

此脚本负责:
1. 读取 .evoskill/config.toml 配置（迭代次数、frontier大小、并发数）
2. 执行进化循环：生成→评估→选择→变异
3. 记录进化历史到 reports/evolution-reports/
4. 支持frontier管理（保留top-3变体）
5. 支持断点续跑

进化流程:
    ┌─────────┐
    │  初始化  │
    └────┬────┘
         ▼
    ┌─────────┐     ┌─────────┐
    │  生成   │────▶│  评估   │
    └────┬────┘     └────┬────┘
         │               │
         ▼               ▼
    ┌─────────┐     ┌─────────┐
    │  选择   │◀────│  变异   │
    └────┬────┘     └─────────┘
         │
         ▼
    ┌─────────┐
    │ 收敛？  │───否──▶ 继续
    └────┬────┘
         │是
         ▼
    ┌─────────┐
    │  输出   │
    └─────────┘

用法:
    python run_evolution.py --config .evoskill/config.toml --skill telephony-bug-analyzer
    python run_evolution.py --skill display-adapter --resume --max-iterations 20
"""

import sys
import argparse
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import toml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# 全局控制台实例
console = Console()


@dataclass
class EvolutionConfig:
    """进化配置数据类"""
    max_iterations: int = 10
    frontier_size: int = 3
    population_size: int = 10
    mutation_rate: float = 0.1
    crossover_rate: float = 0.7
    elite_ratio: float = 0.1
    convergence_threshold: float = 0.01
    checkpoint_interval: int = 5

    @classmethod
    def from_file(cls, file_path: Path) -> 'EvolutionConfig':
        """从TOML文件加载配置"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = toml.load(f)
        return cls(**data.get('evolution', {}))


@dataclass
class SkillVariant:
    """Skill变体数据类"""
    id: str
    generation: int
    fitness: float = 0.0
    parent_ids: List[str] = field(default_factory=list)
    genes: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __lt__(self, other):
        """用于排序（按适应度降序）"""
        return self.fitness > other.fitness


@dataclass
class EvolutionHistory:
    """进化历史数据类"""
    skill_name: str
    config: EvolutionConfig
    current_iteration: int = 0
    population: List[SkillVariant] = field(default_factory=list)
    frontier: List[SkillVariant] = field(default_factory=list)
    best_fitness: float = 0.0
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    generations: List[Dict] = field(default_factory=list)

    def save(self, path: Path):
        """保存历史记录"""
        data = {
            "skill_name": self.skill_name,
            "config": {
                "max_iterations": self.config.max_iterations,
                "frontier_size": self.config.frontier_size,
                "population_size": self.config.population_size,
            },
            "current_iteration": self.current_iteration,
            "best_fitness": self.best_fitness,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "generations": self.generations,
            "frontier": [
                {
                    "id": v.id,
                    "generation": v.generation,
                    "fitness": v.fitness,
                    "genes": v.genes,
                }
                for v in self.frontier
            ]
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: Path, config: EvolutionConfig) -> 'EvolutionHistory':
        """加载历史记录"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        history = cls(
            skill_name=data["skill_name"],
            config=config,
            current_iteration=data["current_iteration"],
            best_fitness=data["best_fitness"],
            start_time=data["start_time"],
            end_time=data.get("end_time"),
        )

        # 恢复frontier
        for v_data in data.get("frontier", []):
            variant = SkillVariant(
                id=v_data["id"],
                generation=v_data["generation"],
                fitness=v_data["fitness"],
                genes=v_data.get("genes", {}),
            )
            history.frontier.append(variant)

        return history


class FitnessEvaluator:
    """适应度评估器"""

    def __init__(self, skill_name: str):
        """
        初始化评估器

        Args:
            skill_name: Skill名称
        """
        self.skill_name = skill_name

    def evaluate(self, variant: SkillVariant) -> float:
        """
        评估变体适应度

        Args:
            variant: Skill变体

        Returns:
            适应度分数 (0.0 - 1.0)
        """
        # 这里是模拟评估，实际应该调用真实的评估逻辑
        # 在真实场景中，这里会调用 evaluate.py 来获取评估结果
        base_fitness = 0.5 + random.random() * 0.4  # 0.5 - 0.9

        # 添加一些随机性来模拟进化
        generation_bonus = variant.generation * 0.01
        noise = random.uniform(-0.05, 0.05)

        fitness = min(1.0, max(0.0, base_fitness + generation_bonus + noise))
        return fitness


class MutationOperator:
    """变异算子"""

    @staticmethod
    def mutate(variant: SkillVariant, config: EvolutionConfig) -> SkillVariant:
        """
        对变体进行变异

        Args:
            variant: 原始变体
            config: 进化配置

        Returns:
            变异后的新变体
        """
        if random.random() > config.mutation_rate:
            return variant

        # 创建新变体
        new_variant = SkillVariant(
            id=f"{variant.id}_m{random.randint(1000, 9999)}",
            generation=variant.generation + 1,
            parent_ids=[variant.id],
            genes=variant.genes.copy(),
            metadata=variant.metadata.copy(),
        )

        # 执行变异操作
        if random.random() < 0.5:
            # 参数调整
            MutationOperator._adjust_parameters(new_variant)
        else:
            # 规则修改
            MutationOperator._modify_rules(new_variant)

        return new_variant

    @staticmethod
    def _adjust_parameters(variant: SkillVariant):
        """调整参数"""
        params = variant.genes.get("parameters", {})
        if not params:
            params = {
                "threshold": 0.5,
                "max_retries": 3,
                "timeout": 30,
            }

        # 随机调整一个参数
        param_name = random.choice(list(params.keys()))
        param_value = params[param_name]

        if isinstance(param_value, (int, float)):
            delta = param_value * random.uniform(-0.2, 0.2)
            params[param_name] = param_value + delta

        variant.genes["parameters"] = params

    @staticmethod
    def _modify_rules(variant: SkillVariant):
        """修改规则"""
        rules = variant.genes.get("rules", [])
        if not rules:
            rules = []

        if random.random() < 0.5 and rules:
            # 删除一条规则
            rules.pop(random.randint(0, len(rules) - 1))
        else:
            # 添加一条新规则
            rules.append({
                "pattern": f"rule_{random.randint(1000, 9999)}",
                "condition": "always",
                "action": "pass",
            })

        variant.genes["rules"] = rules


class CrossoverOperator:
    """交叉算子"""

    @staticmethod
    def crossover(
        parent1: SkillVariant,
        parent2: SkillVariant,
        config: EvolutionConfig
    ) -> Optional[SkillVariant]:
        """
        对两个变体进行交叉

        Args:
            parent1: 父本1
            parent2: 父本2
            config: 进化配置

        Returns:
            交叉后的新变体，或None（如果未进行交叉）
        """
        if random.random() > config.crossover_rate:
            return None

        # 创建新变体
        new_variant = SkillVariant(
            id=f"{parent1.id[:8]}_{parent2.id[:8]}_c{random.randint(1000, 9999)}",
            generation=max(parent1.generation, parent2.generation) + 1,
            parent_ids=[parent1.id, parent2.id],
            genes={},
            metadata={}
        )

        # 基因重组
        genes1 = parent1.genes
        genes2 = parent2.genes

        all_keys = set(genes1.keys()) | set(genes2.keys())
        for key in all_keys:
            if random.random() < 0.5 and key in genes1:
                new_variant.genes[key] = genes1[key]
            elif key in genes2:
                new_variant.genes[key] = genes2[key]

        return new_variant


class EvolutionManager:
    """进化管理器"""

    def __init__(
        self,
        skill_name: str,
        config: EvolutionConfig,
        base_path: Path = None
    ):
        """
        初始化进化管理器

        Args:
            skill_name: Skill名称
            config: 进化配置
            base_path: 基础路径
        """
        self.skill_name = skill_name
        self.config = config
        self.base_path = base_path or Path("E:/TAHP/tahp")

        self.reports_path = self.base_path / "reports" / "evolution-reports"
        self.checkpoint_path = self.base_path / ".evoskill" / "checkpoints"

        self.evaluator = FitnessEvaluator(skill_name)
        self.mutator = MutationOperator()
        self.crossover = CrossoverOperator()

        self.history: Optional[EvolutionHistory] = None

    def _init_population(self) -> List[SkillVariant]:
        """初始化种群"""
        population = []

        for i in range(self.config.population_size):
            variant = SkillVariant(
                id=f"{self.skill_name}_gen0_{i:03d}",
                generation=0,
                fitness=0.0,
                genes={
                    "parameters": {
                        "threshold": 0.5 + random.random() * 0.3,
                        "max_retries": random.randint(2, 5),
                        "timeout": random.randint(20, 60),
                    },
                    "rules": []
                },
            )
            population.append(variant)

        return population

    def _select_parents(
        self,
        population: List[SkillVariant]
    ) -> List[SkillVariant]:
        """选择父本（轮盘赌选择）"""
        total_fitness = sum(v.fitness for v in population)
        if total_fitness == 0:
            return random.sample(population, 2)

        weights = [v.fitness / total_fitness for v in population]
        return random.choices(population, weights=weights, k=2)

    def _evolve_generation(
        self,
        population: List[SkillVariant]
    ) -> List[SkillVariant]:
        """
        进化一代

        Args:
            population: 当前种群

        Returns:
            新种群
        """
        new_population = []

        # 保留精英
        elite_count = int(self.config.population_size * self.config.elite_ratio)
        sorted_pop = sorted(population, reverse=True)
        new_population.extend(sorted_pop[:elite_count])

        # 生成新个体
        while len(new_population) < self.config.population_size:
            # 选择父本
            parent1, parent2 = self._select_parents(population)

            # 交叉
            child = self.crossover.crossover(parent1, parent2, self.config)

            if child is None:
                # 未交叉，直接变异
                child = self.mutator.mutate(parent1, self.config)

            # 评估
            child.fitness = self.evaluator.evaluate(child)
            new_population.append(child)

        return new_population

    def _update_frontier(self, population: List[SkillVariant]):
        """更新frontier（保留top-N最优变体）"""
        sorted_pop = sorted(population, reverse=True)
        self.history.frontier = sorted_pop[:self.config.frontier_size]

        if sorted_pop:
            self.history.best_fitness = sorted_pop[0].fitness

    def _check_convergence(self) -> bool:
        """检查是否收敛"""
        if len(self.history.generations) < 2:
            return False

        recent_fitness = [
            g["best_fitness"]
            for g in self.history.generations[-5:]
        ]

        if len(recent_fitness) < 5:
            return False

        # 检查最近几代的最优适应度是否变化很小
        max_diff = max(recent_fitness) - min(recent_fitness)
        return max_diff < self.config.convergence_threshold

    def _save_checkpoint(self):
        """保存检查点"""
        self.checkpoint_path.mkdir(parents=True, exist_ok=True)
        checkpoint_file = self.checkpoint_path / f"{self.skill_name}_checkpoint.json"
        self.history.save(checkpoint_file)

    def run(
        self,
        resume: bool = False,
        max_iterations: Optional[int] = None
    ) -> EvolutionHistory:
        """
        运行进化循环

        Args:
            resume: 是否从检查点恢复
            max_iterations: 最大迭代次数（覆盖配置）

        Returns:
            进化历史
        """
        # 初始化历史记录
        if resume and self._has_checkpoint():
            console.print("[cyan]从检查点恢复...[/cyan]")
            self.history = self._load_checkpoint()
            start_iter = self.history.current_iteration
        else:
            max_iters = max_iterations or self.config.max_iterations
            self.history = EvolutionHistory(
                skill_name=self.skill_name,
                config=EvolutionConfig(
                    max_iterations=max_iters,
                    frontier_size=self.config.frontier_size,
                    population_size=self.config.population_size,
                )
            )
            self.history.population = self._init_population()
            start_iter = 0

        console.print(f"\n[bold cyan]开始进化: {self.skill_name}[/bold cyan]")
        console.print(f"最大迭代次数: {self.history.config.max_iterations}")
        console.print(f"种群大小: {self.history.config.population_size}")
        console.print(f"Frontier大小: {self.history.config.frontier_size}")

        # 进化循环
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]进化中...",
                total=self.history.config.max_iterations - start_iter
            )

            for iteration in range(start_iter, self.history.config.max_iterations):
                self.history.current_iteration = iteration

                # 评估当前种群
                for variant in self.history.population:
                    if variant.fitness == 0:
                        variant.fitness = self.evaluator.evaluate(variant)

                # 更新frontier
                self._update_frontier(self.history.population)

                # 记录这一代的信息
                generation_info = {
                    "iteration": iteration,
                    "best_fitness": self.history.best_fitness,
                    "avg_fitness": sum(v.fitness for v in self.history.population) /
                                   len(self.history.population),
                    "population_size": len(self.history.population),
                }
                self.history.generations.append(generation_info)

                # 显示进度
                progress.update(
                    task,
                    description=f"[cyan]最佳适应度: {self.history.best_fitness:.3f}"
                )
                progress.update(task, advance=1)

                # 保存检查点
                if (iteration + 1) % self.history.config.checkpoint_interval == 0:
                    self._save_checkpoint()
                    console.print(f"\n[dim]检查点已保存 (迭代 {iteration + 1})[/dim]")

                # 检查收敛
                if self._check_convergence():
                    console.print("\n[green]检测到收敛，进化完成[/green]")
                    break

                # 进化下一代
                self.history.population = self._evolve_generation(
                    self.history.population
                )

        # 完成
        self.history.end_time = datetime.now().isoformat()
        self._save_checkpoint()
        self._save_report()

        console.print(f"\n[bold green]进化完成![/bold green]")
        console.print(f"最终最佳适应度: {self.history.best_fitness:.3f}")
        console.print(f"总迭代次数: {self.history.current_iteration + 1}")

        return self.history

    def _has_checkpoint(self) -> bool:
        """检查是否存在检查点"""
        checkpoint_file = self.checkpoint_path / f"{self.skill_name}_checkpoint.json"
        return checkpoint_file.exists()

    def _load_checkpoint(self) -> EvolutionHistory:
        """加载检查点"""
        checkpoint_file = self.checkpoint_path / f"{self.skill_name}_checkpoint.json"
        return EvolutionHistory.load(checkpoint_file, self.config)

    def _save_report(self):
        """保存最终报告"""
        self.reports_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.reports_path / f"{self.skill_name}_{timestamp}.json"

        self.history.save(report_file)
        console.print(f"[green]进化报告已保存: {report_file}[/green]")


def print_frontier_table(frontier: List[SkillVariant]):
    """打印frontier表格"""
    table = Table(title="Frontier (Top Variants)")
    table.add_column("ID", style="cyan")
    table.add_column("Generation", justify="right")
    table.add_column("Fitness", justify="right", style="green")
    table.add_column("Parent IDs")

    for variant in frontier:
        table.add_row(
            variant.id,
            str(variant.generation),
            f"{variant.fitness:.4f}",
            ", ".join(variant.parent_ids) if variant.parent_ids else "-"
        )

    console.print(table)


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description="TAHP EvoSkill 进化管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_evolution.py --config .evoskill/config.toml --skill telephony-bug-analyzer
  python run_evolution.py --skill display-adapter --resume
  python run_evolution.py --skill audio-driver --max-iterations 20
        """
    )

    parser.add_argument("--config", "-c", type=str, help="配置文件路径")
    parser.add_argument("--skill", "-s", required=True, help="Skill名称")
    parser.add_argument("--max-iterations", "-i", type=int, help="最大迭代次数")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从检查点恢复"
    )
    parser.add_argument(
        "--base-path",
        type=str,
        default="E:/TAHP/tahp",
        help="基础路径"
    )

    args = parser.parse_args()

    # 加载配置
    if args.config:
        config = EvolutionConfig.from_file(Path(args.config))
    else:
        # 使用默认配置
        config = EvolutionConfig()

    if args.max_iterations:
        config.max_iterations = args.max_iterations

    # 创建进化管理器
    manager = EvolutionManager(
        skill_name=args.skill,
        config=config,
        base_path=Path(args.base_path)
    )

    # 运行进化
    history = manager.run(resume=args.resume)

    # 显示frontier
    if history.frontier:
        console.print("\n")
        print_frontier_table(history.frontier)


if __name__ == "__main__":
    main()
