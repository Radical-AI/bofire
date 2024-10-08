import math
from itertools import chain

import numpy as np
import pandas as pd
import pytest
import torch
from botorch.acquisition import (
    qExpectedImprovement,
    qLogExpectedImprovement,
    qLogNoisyExpectedImprovement,
    qNoisyExpectedImprovement,
    qProbabilityOfImprovement,
    qSimpleRegret,
    qUpperConfidenceBound,
)
from botorch.acquisition.objective import ConstrainedMCObjective, GenericMCObjective

import bofire.data_models.strategies.api as data_models
import tests.bofire.data_models.specs.api as specs
from bofire.benchmarks.api import Branin
from bofire.benchmarks.multi import DTLZ2
from bofire.benchmarks.single import Himmelblau, _CategoricalDiscreteHimmelblau
from bofire.data_models.acquisition_functions.api import (
    AnySingleObjectiveAcquisitionFunction,
    SingleObjectiveAcquisitionFunction,
    qEI,
    qLogEI,
    qLogNEI,
    qNEI,
    qPI,
    qSR,
    qUCB,
)
from bofire.data_models.constraints.api import (
    InterpointEqualityConstraint,
    NChooseKConstraint,
)
from bofire.data_models.domain.api import Domain, Inputs, Outputs
from bofire.data_models.features.api import ContinuousInput, ContinuousOutput
from bofire.data_models.objectives.api import (
    MaximizeObjective,
    MaximizeSigmoidObjective,
)
from bofire.data_models.strategies.api import LSRBO
from bofire.data_models.strategies.api import RandomStrategy as RandomStrategyDataModel
from bofire.data_models.unions import to_list
from bofire.strategies.api import CustomSoboStrategy, RandomStrategy, SoboStrategy
from tests.bofire.strategies.test_base import domains


# from tests.bofire.strategies.botorch.test_model_spec import VALID_MODEL_SPEC_LIST

VALID_BOTORCH_SOBO_STRATEGY_SPEC = {
    "domain": domains[1],
    "acquisition_function": specs.acquisition_functions.valid(
        SingleObjectiveAcquisitionFunction, exact=False
    ).obj(),
    # "num_sobol_samples": 1024,
    # "num_restarts": 8,
    # "num_raw_samples": 1024,
    "descriptor_method": "EXHAUSTIVE",
    "categorical_method": "EXHAUSTIVE",
}

BOTORCH_SOBO_STRATEGY_SPECS = {
    "valids": [
        VALID_BOTORCH_SOBO_STRATEGY_SPEC,
        {**VALID_BOTORCH_SOBO_STRATEGY_SPEC, "seed": 1},
        # {**VALID_BOTORCH_SOBO_STRATEGY_SPEC, "surrogate_specs": VALID_MODEL_SPEC_LIST},
    ],
    "invalids": [
        {**VALID_BOTORCH_SOBO_STRATEGY_SPEC, "acquisition_function": None},
        {**VALID_BOTORCH_SOBO_STRATEGY_SPEC, "descriptor_method": None},
        {**VALID_BOTORCH_SOBO_STRATEGY_SPEC, "categorical_method": None},
        {**VALID_BOTORCH_SOBO_STRATEGY_SPEC, "seed": -1},
    ],
}

VALID_ADDITIVE_AND_MULTIPLICATIVE_BOTORCH_SOBO_STRATEGY_SPEC = {
    "domain": domains[2],
    "acquisition_function": specs.acquisition_functions.valid(
        SingleObjectiveAcquisitionFunction, exact=False
    ).obj(),
    "descriptor_method": "EXHAUSTIVE",
    "categorical_method": "EXHAUSTIVE",
}

BOTORCH_ADDITIVE_AND_MULTIPLICATIVE_SOBO_STRATEGY_SPECS = {
    "valids": [
        VALID_ADDITIVE_AND_MULTIPLICATIVE_BOTORCH_SOBO_STRATEGY_SPEC,
        {**VALID_ADDITIVE_AND_MULTIPLICATIVE_BOTORCH_SOBO_STRATEGY_SPEC, "seed": 1},
    ],
    "invalids": [
        {
            **VALID_ADDITIVE_AND_MULTIPLICATIVE_BOTORCH_SOBO_STRATEGY_SPEC,
            "acquisition_function": None,
        },
        {
            **VALID_ADDITIVE_AND_MULTIPLICATIVE_BOTORCH_SOBO_STRATEGY_SPEC,
            "descriptor_method": None,
        },
        {
            **VALID_ADDITIVE_AND_MULTIPLICATIVE_BOTORCH_SOBO_STRATEGY_SPEC,
            "categorical_method": None,
        },
        {**VALID_ADDITIVE_AND_MULTIPLICATIVE_BOTORCH_SOBO_STRATEGY_SPEC, "seed": -1},
    ],
}


@pytest.mark.parametrize(
    "domain, acqf",
    [(domains[0], VALID_BOTORCH_SOBO_STRATEGY_SPEC["acquisition_function"])],
)
def test_SOBO_not_fitted(domain, acqf):
    data_model = data_models.SoboStrategy(domain=domain, acquisition_function=acqf)
    strategy = SoboStrategy(data_model=data_model)

    msg = "Model not trained."
    with pytest.raises(AssertionError, match=msg):
        strategy._get_acqfs(2)


@pytest.mark.parametrize(
    "acqf, expected, num_test_candidates",
    [
        (acqf_inp[0], acqf_inp[1], num_test_candidates)
        for acqf_inp in [
            (qEI(), qExpectedImprovement),
            (qNEI(), qNoisyExpectedImprovement),
            (qPI(), qProbabilityOfImprovement),
            (qUCB(), qUpperConfidenceBound),
            (qSR(), qSimpleRegret),
            (qLogEI(), qLogExpectedImprovement),
            (qLogNEI(), qLogNoisyExpectedImprovement),
        ]
        for num_test_candidates in range(1, 3)
    ],
)
def test_SOBO_get_acqf(acqf, expected, num_test_candidates):
    # generate data
    benchmark = Himmelblau()

    random_strategy = RandomStrategy(
        data_model=RandomStrategyDataModel(domain=benchmark.domain)
    )

    experiments = benchmark.f(random_strategy.ask(20), return_complete=True)

    data_model = data_models.SoboStrategy(
        domain=benchmark.domain, acquisition_function=acqf
    )
    strategy = SoboStrategy(data_model=data_model)

    strategy.tell(experiments)

    acqfs = strategy._get_acqfs(2)
    assert len(acqfs) == 1

    assert isinstance(acqfs[0], expected)


def test_SOBO_calc_acquisition():
    benchmark = Himmelblau()
    experiments = benchmark.f(benchmark.domain.inputs.sample(10), return_complete=True)
    samples = benchmark.domain.inputs.sample(2)
    data_model = data_models.SoboStrategy(
        domain=benchmark.domain, acquisition_function=qEI()
    )
    strategy = SoboStrategy(data_model=data_model)
    strategy.tell(experiments=experiments)
    vals = strategy.calc_acquisition(samples)
    assert len(vals) == 2
    vals = strategy.calc_acquisition(samples, combined=True)
    assert len(vals) == 1


def test_SOBO_init_qUCB():
    beta = 0.5
    acqf = qUCB(beta=beta)

    # generate data
    benchmark = Himmelblau()
    random_strategy = RandomStrategy(
        data_model=RandomStrategyDataModel(domain=benchmark.domain)
    )
    experiments = benchmark.f(random_strategy.ask(20), return_complete=True)

    data_model = data_models.SoboStrategy(
        domain=benchmark.domain, acquisition_function=acqf
    )
    strategy = SoboStrategy(data_model=data_model)
    strategy.tell(experiments)

    acqf = strategy._get_acqfs(2)[0]
    assert acqf.beta_prime == math.sqrt(beta * math.pi / 2)


@pytest.mark.parametrize(
    "acqf, num_experiments, num_candidates",
    [
        (acqf.obj(), num_experiments, num_candidates)
        for acqf in specs.acquisition_functions.valids
        for num_experiments in range(8, 10)
        for num_candidates in range(1, 3)
        if isinstance(acqf, to_list(AnySingleObjectiveAcquisitionFunction))  # type: ignore
    ],
)
@pytest.mark.slow
def test_get_acqf_input(acqf, num_experiments, num_candidates):
    # generate data
    benchmark = Himmelblau()
    random_strategy = RandomStrategy(
        data_model=RandomStrategyDataModel(domain=benchmark.domain)
    )
    experiments = benchmark.f(
        random_strategy._ask(candidate_count=num_experiments),
        return_complete=True,  # type: ignore
    )

    data_model = data_models.SoboStrategy(
        domain=benchmark.domain, acquisition_function=acqf
    )
    strategy = SoboStrategy(data_model=data_model)

    strategy.tell(experiments)
    strategy.ask(candidate_count=num_candidates, add_pending=True)

    X_train, X_pending = strategy.get_acqf_input_tensors()

    _, names = strategy.domain.inputs._get_transform_info(
        specs=strategy.surrogate_specs.input_preprocessing_specs
    )

    assert torch.is_tensor(X_train)
    assert torch.is_tensor(X_pending)
    assert X_train.shape == (
        num_experiments,
        len(set(chain(*names.values()))),
    )
    assert X_pending.shape == (  # type: ignore
        num_candidates,
        len(set(chain(*names.values()))),
    )


def test_custom_get_objective():
    def f(samples, callables, weights, X):
        outputs_list = []
        for c, w in zip(callables, weights):
            outputs_list.append(c(samples, None) ** w)
        samples = torch.stack(outputs_list, dim=-1)

        return (samples[..., 0] + samples[..., 1]) * (samples[..., 0] * samples[..., 1])

    benchmark = DTLZ2(3)
    experiments = benchmark.f(benchmark.domain.inputs.sample(5), return_complete=True)
    data_model = data_models.CustomSoboStrategy(
        domain=benchmark.domain, acquisition_function=qNEI()
    )
    strategy = CustomSoboStrategy(data_model=data_model)
    strategy.f = f
    strategy._experiments = experiments
    generic_objective, _, _ = strategy._get_objective_and_constraints()
    assert isinstance(generic_objective, GenericMCObjective)


def test_custom_get_objective_invalid():
    benchmark = DTLZ2(3)
    data_model = data_models.CustomSoboStrategy(
        domain=benchmark.domain, acquisition_function=qNEI()
    )
    strategy = CustomSoboStrategy(data_model=data_model)
    experiments = benchmark.f(benchmark.domain.inputs.sample(5), return_complete=True)
    strategy._experiments = experiments

    with pytest.raises(ValueError):
        strategy._get_objective_and_constraints()


def test_custom_dumps_loads():
    def f(samples, callables, weights, X):
        outputs_list = []
        for c, w in zip(callables, weights):
            outputs_list.append(c(samples, None) ** w)
        samples = torch.stack(outputs_list, dim=-1)

        return (samples[..., 0] + samples[..., 1]) * (samples[..., 0] * samples[..., 1])

    benchmark = DTLZ2(3)
    data_model1 = data_models.CustomSoboStrategy(
        domain=benchmark.domain,
        acquisition_function=qNEI(),
        use_output_constraints=False,
    )
    strategy1 = CustomSoboStrategy(data_model=data_model1)
    experiments = benchmark.f(benchmark.domain.inputs.sample(5), return_complete=True)
    strategy1._experiments = experiments
    strategy1.f = f
    f_str = strategy1.dumps()

    data_model2 = data_models.CustomSoboStrategy(
        domain=benchmark.domain,
        acquisition_function=qNEI(),
        use_output_constraints=False,
        dump=f_str,
    )
    strategy2 = CustomSoboStrategy(data_model=data_model2)
    strategy2._experiments = experiments

    data_model3 = data_models.CustomSoboStrategy(
        domain=benchmark.domain, acquisition_function=qNEI()
    )
    strategy3 = CustomSoboStrategy(data_model=data_model3)
    strategy3._experiments = experiments
    strategy3.loads(f_str)

    assert isinstance(strategy2.f, type(f))
    assert isinstance(strategy3.f, type(f))

    samples = torch.rand(30, 2, requires_grad=True) * 5
    objective1, _, _ = strategy1._get_objective_and_constraints()
    output1 = objective1.forward(samples)
    objective2, _, _ = strategy2._get_objective_and_constraints()
    output2 = objective2.forward(samples)
    objective3, _, _ = strategy3._get_objective_and_constraints()
    output3 = objective3.forward(samples)

    torch.testing.assert_close(output1, output2)
    torch.testing.assert_close(output1, output3)


def test_custom_dumps_invalid():
    benchmark = DTLZ2(3)
    data_model = data_models.CustomSoboStrategy(
        domain=benchmark.domain, acquisition_function=qNEI()
    )
    strategy = CustomSoboStrategy(data_model=data_model)
    with pytest.raises(ValueError):
        strategy.dumps()


@pytest.mark.parametrize("candidate_count", [1, 2])
def test_sobo_fully_combinatorical(candidate_count):
    benchmark = _CategoricalDiscreteHimmelblau()

    strategy_data = data_models.SoboStrategy(domain=benchmark.domain)
    strategy = SoboStrategy(data_model=strategy_data)

    experiments = benchmark.f(benchmark.domain.inputs.sample(10), return_complete=True)

    strategy.tell(experiments=experiments)
    strategy.ask(candidate_count=candidate_count)


@pytest.mark.parametrize(
    "outputs, expected_objective",
    [
        (
            Outputs(
                features=[ContinuousOutput(key="alpha", objective=MaximizeObjective())]
            ),
            GenericMCObjective,
        ),
        (
            Outputs(
                features=[
                    ContinuousOutput(
                        key="alpha",
                        objective=MaximizeSigmoidObjective(steepness=1, tp=1),
                    )
                ]
            ),
            GenericMCObjective,
        ),
    ],
)
def test_sobo_get_objective(outputs, expected_objective):
    strategy_data = data_models.SoboStrategy(
        domain=Domain(
            inputs=Inputs(features=[ContinuousInput(key="a", bounds=(0, 1))]),
            outputs=outputs,
        )
    )
    experiments = pd.DataFrame({"a": [0.5], "alpha": [0.5], "valid_alpha": [1]})
    strategy = SoboStrategy(data_model=strategy_data)
    strategy._experiments = experiments
    obj, _, _ = strategy._get_objective_and_constraints()
    assert isinstance(obj, expected_objective)


def test_sobo_get_constrained_objective():
    benchmark = DTLZ2(dim=6)
    experiments = benchmark.f(benchmark.domain.inputs.sample(5), return_complete=True)
    domain = benchmark.domain
    domain.outputs.get_by_key("f_1").objective = MaximizeSigmoidObjective(  # type: ignore
        tp=1.5, steepness=2.0
    )
    strategy_data = data_models.SoboStrategy(domain=domain, acquisition_function=qUCB())
    strategy = SoboStrategy(data_model=strategy_data)
    strategy.tell(experiments=experiments)
    obj, _, _ = strategy._get_objective_and_constraints()
    assert isinstance(obj, ConstrainedMCObjective)


def test_sobo_get_constrained_objective2():
    benchmark = DTLZ2(dim=6)
    experiments = benchmark.f(benchmark.domain.inputs.sample(5), return_complete=True)
    domain = benchmark.domain
    domain.outputs.get_by_key("f_1").objective = MaximizeSigmoidObjective(  # type: ignore
        tp=1.5, steepness=2.0
    )
    strategy_data = data_models.SoboStrategy(domain=domain, acquisition_function=qEI())
    strategy = SoboStrategy(data_model=strategy_data)
    strategy.tell(experiments=experiments)
    obj, _, _ = strategy._get_objective_and_constraints()
    assert isinstance(obj, GenericMCObjective)


def test_sobo_hyperoptimize():
    benchmark = Himmelblau()
    experiments = benchmark.f(benchmark.domain.inputs.sample(3), return_complete=True)
    strategy_data = data_models.SoboStrategy(
        domain=benchmark.domain, acquisition_function=qEI(), frequency_hyperopt=1
    )
    strategy_data.surrogate_specs.surrogates[0].hyperconfig = None  # type: ignore
    strategy = SoboStrategy(data_model=strategy_data)
    with pytest.warns(
        match="No hyperopt is possible as no hyperopt config is available. Returning initial config."
    ):
        strategy.tell(experiments=experiments)


def test_sobo_lsrbo():
    bench = Branin(locality_factor=0.5)
    experiments = bench.f(bench.domain.inputs.sample(3, seed=42), return_complete=True)
    # without lsr
    strategy_data = data_models.SoboStrategy(domain=bench.domain, seed=42)
    strategy = SoboStrategy(data_model=strategy_data)
    strategy.tell(experiments)
    candidates = strategy.ask(1)
    candidates.loc[
        (
            (candidates.x_1 > experiments.loc[2, "x_1"] + 0.25)  # type: ignore
            | (candidates.x_1 < experiments.loc[2, "x_1"] - 0.25)  # type: ignore
        )
        & (
            (candidates.x_1 > experiments.loc[2, "x_2"] + 0.75)  # type: ignore
            | (candidates.x_1 < experiments.loc[2, "x_2"] - 0.75)  # type: ignore
        )
    ]
    # local search
    strategy_data = data_models.SoboStrategy(
        domain=bench.domain, seed=42, local_search_config=LSRBO(gamma=0)
    )
    strategy = SoboStrategy(data_model=strategy_data)
    strategy.tell(experiments)
    strategy.ask(1)
    np.allclose(candidates.loc[0, ["x_1", "x_2"]].tolist(), [-2.55276, 11.192913])  # type: ignore
    # global search
    strategy_data = data_models.SoboStrategy(
        domain=bench.domain, seed=42, local_search_config=LSRBO(gamma=500000)
    )
    strategy = SoboStrategy(data_model=strategy_data)
    strategy.tell(experiments)
    strategy.ask(1)
    np.allclose(candidates.loc[0, ["x_1", "x_2"]].tolist(), [-2.05276, 11.192913])  # type: ignore


def test_sobo_get_optimizer_options():
    domain = Domain(
        inputs=[  # type: ignore
            ContinuousInput(key="a", bounds=(0, 1)),
            ContinuousInput(key="b", bounds=(0, 1)),
        ],
        outputs=[ContinuousOutput(key="c")],  # type: ignore
    )
    strategy_data = data_models.SoboStrategy(domain=domain, maxiter=500, batch_limit=4)
    strategy = SoboStrategy(data_model=strategy_data)
    assert strategy._get_optimizer_options() == {"maxiter": 500, "batch_limit": 4}
    domain = Domain(
        inputs=[  # type: ignore
            ContinuousInput(key="a", bounds=(0, 1)),
            ContinuousInput(key="b", bounds=(0, 1)),
        ],
        outputs=[ContinuousOutput(key="c")],  # type: ignore
        constraints=[  # type: ignore
            NChooseKConstraint(
                features=["a", "b"], max_count=1, min_count=0, none_also_valid=True
            )
        ],
    )
    strategy_data = data_models.SoboStrategy(domain=domain, maxiter=500, batch_limit=4)
    strategy = SoboStrategy(data_model=strategy_data)
    assert strategy._get_optimizer_options() == {"maxiter": 500, "batch_limit": 1}


def test_sobo_interpoint():
    bench = Himmelblau()
    experiments = bench.f(bench.domain.inputs.sample(4), return_complete=True)
    domain = bench._domain
    domain.constraints.constraints.append(InterpointEqualityConstraint(feature="x_1"))  # type: ignore
    strategy_data = data_models.SoboStrategy(domain=domain)
    strategy = SoboStrategy(data_model=strategy_data)
    strategy.tell(experiments)
    strategy.ask(2)
