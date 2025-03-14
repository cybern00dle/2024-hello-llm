"""
Fine-tuning starter.
"""
# pylint: disable=too-many-locals, undefined-variable, unused-import, too-many-branches, too-many-statements
from pathlib import Path

import pandas as pd
from transformers import AutoTokenizer, set_seed

from config.constants import PROJECT_ROOT
from config.lab_settings import LabSettings, SFTParams
from core_utils.llm.time_decorator import report_time
from lab_8_sft.main import (
    LLMPipeline,
    RawDataImporter,
    RawDataPreprocessor,
    SFTPipeline,
    TaskDataset,
    TaskEvaluator,
    TokenizedTaskDataset,
)


@report_time
def main() -> None:
    """
    Run the translation pipeline.
    """
    lab_path = PROJECT_ROOT / 'lab_8_sft'

    settings = LabSettings(lab_path / 'settings.json')

    dist_path = lab_path / 'dist'
    dist_path.mkdir(exist_ok=True)
    predictions_path = dist_path / 'predictions.csv'

    importer = RawDataImporter(settings.parameters.dataset)
    importer.obtain()

    if not isinstance(importer.raw_data, pd.DataFrame):
        raise TypeError('The downloaded dataset is not pd.DataFrame.')

    preprocessor = RawDataPreprocessor(importer.raw_data)
    preprocessor.analyze()
    preprocessor.transform()

    dataset = TaskDataset(preprocessor.data.head(100))

    pipeline = LLMPipeline(
        settings.parameters.model,
        dataset,
        max_length=120,
        batch_size=64,
        device='cpu'
    )
    pipeline.analyze_model()
    pipeline.infer_sample(dataset[0])

    dataset_inference = pipeline.infer_dataset()
    dataset_inference.to_csv(predictions_path)

    evaluator = TaskEvaluator(predictions_path, settings.parameters.metrics)
    metrics = evaluator.run()
    print(metrics)

    set_seed(42)

    sft_params = SFTParams(
        batch_size=3,
        max_length=120,
        max_fine_tuning_steps=50,
        device='cpu',
        finetuned_model_path=dist_path / settings.parameters.model,
        learning_rate=1e-3,
        target_modules=['query', 'key', 'value']
    )

    num_samples = 10
    fine_tune_samples = sft_params.batch_size * sft_params.max_fine_tuning_steps
    sft_dataset = TokenizedTaskDataset(preprocessor.data.loc[
                                   num_samples: num_samples + fine_tune_samples
                                   ],
                                   AutoTokenizer.from_pretrained(settings.parameters.model),
                                   sft_params.max_length)

    sft_pipeline = SFTPipeline(settings.parameters.model, sft_dataset, sft_params)
    sft_pipeline.run()

    tokenizer = AutoTokenizer.from_pretrained(settings.parameters.model)
    tokenizer.save_pretrained(sft_params.finetuned_model_path)

    finetuned_pipeline = LLMPipeline(
        str(sft_params.finetuned_model_path),
        TaskDataset(preprocessor.data.head(10)),
        max_length=120,
        batch_size=64,
        device='cpu'
    )
    finetuned_pipeline.analyze_model()
    finetuned_pipeline.infer_sample(sft_dataset[0])

    sft_dataset_inference = finetuned_pipeline.infer_dataset()
    sft_dataset_inference.to_csv(predictions_path)

    finetuned_evaluator = TaskEvaluator(predictions_path, settings.parameters.metrics)
    finetuned_metrics = finetuned_evaluator.run()
    print(finetuned_metrics)

    result = finetuned_metrics
    assert result is not None, "Finetuning does not work correctly"


if __name__ == "__main__":
    main()
