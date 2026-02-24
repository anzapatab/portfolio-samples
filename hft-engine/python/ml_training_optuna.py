# Extract from HFT Quant Engine
# ML training pipeline with Optuna hyperparameter optimization.
# Uses LightGBM with time-series cross-validation to predict
# forward returns. Exports optimized models for ONNX inference.

#!/usr/bin/env python3
"""
ML Training with Optuna Hyperparameter Optimization

This version uses Optuna to find the best hyperparameters
"""

import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error
import optuna
from optuna.samplers import TPESampler
import joblib
from pathlib import Path
import logging
from feature_engineering import FeatureEngineer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress Optuna's default logging
optuna.logging.set_verbosity(optuna.logging.WARNING)


class MLTrainerOptuna:
    """ML Trainer with Optuna hyperparameter optimization"""

    def __init__(self, model_dir: str = "../models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.feature_columns = None
        self.model = None
        self.best_params = None

    def prepare_data(self, csv_path: str, target: str = 'forward_return_15m'):
        """Load and prepare data"""
        logger.info(f"Loading data from {csv_path}...")

        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows")

        logger.info("Computing features...")
        fe = FeatureEngineer()
        df_features = fe.compute_all_features(df)
        logger.info(f"Computed {fe.feature_count} features")

        exclude_cols = [
            'timestamp', 'symbol', 'exchange',
            'open', 'high', 'low', 'close', 'volume',
            'forward_return_5m', 'forward_return_15m', 'forward_return_1h'
        ]

        self.feature_columns = [c for c in df_features.columns if c not in exclude_cols]

        X = df_features[self.feature_columns].copy()
        y = df_features[target].copy()

        valid_mask = ~y.isna()
        X = X[valid_mask]
        y = y[valid_mask]
        X = X.fillna(0)

        logger.info(f"Prepared {len(X)} samples with {len(self.feature_columns)} features")

        return X, y

    def optimize_hyperparameters(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_trials: int = 50,
        cv_splits: int = 3
    ):
        """
        Find best hyperparameters using Optuna

        Args:
            X: Features
            y: Labels
            n_trials: Number of Optuna trials
            cv_splits: Number of CV folds

        Returns:
            Best parameters dictionary
        """
        logger.info("=" * 60)
        logger.info(f"Starting Optuna Optimization ({n_trials} trials)")
        logger.info("=" * 60)

        def objective(trial):
            """Optuna objective function"""
            params = {
                'objective': 'regression',
                'metric': 'rmse',
                'verbosity': -1,
                'boosting_type': 'gbdt',

                # Parameters to optimize
                'num_leaves': trial.suggest_int('num_leaves', 20, 100),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                'feature_fraction': trial.suggest_float('feature_fraction', 0.4, 1.0),
                'bagging_fraction': trial.suggest_float('bagging_fraction', 0.4, 1.0),
                'bagging_freq': trial.suggest_int('bagging_freq', 1, 7),
                'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
                'lambda_l1': trial.suggest_float('lambda_l1', 1e-8, 10.0, log=True),
                'lambda_l2': trial.suggest_float('lambda_l2', 1e-8, 10.0, log=True),
                'max_depth': trial.suggest_int('max_depth', 3, 12)
            }

            # Time-series cross-validation
            tscv = TimeSeriesSplit(n_splits=cv_splits)
            scores = []

            for train_idx, val_idx in tscv.split(X):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

                train_data = lgb.Dataset(X_train, label=y_train)
                val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

                model = lgb.train(
                    params,
                    train_data,
                    num_boost_round=500,
                    valid_sets=[val_data],
                    callbacks=[
                        lgb.early_stopping(stopping_rounds=50, verbose=False),
                        lgb.log_evaluation(period=0)
                    ]
                )

                y_pred = model.predict(X_val, num_iteration=model.best_iteration)
                rmse = np.sqrt(mean_squared_error(y_val, y_pred))
                scores.append(rmse)

            return np.mean(scores)

        # Run Optuna optimization
        study = optuna.create_study(
            direction='minimize',
            sampler=TPESampler(seed=42)
        )

        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

        logger.info("\n" + "=" * 60)
        logger.info("Optimization Complete!")
        logger.info("=" * 60)
        logger.info(f"Best RMSE: {study.best_value:.6f}")
        logger.info(f"\nBest Parameters:")
        for key, value in study.best_params.items():
            logger.info(f"  {key:20s}: {value}")

        self.best_params = study.best_params

        return study.best_params, study.best_value

    def train_final_model(self, X: pd.DataFrame, y: pd.Series, params: dict = None):
        """
        Train final model with best parameters

        Args:
            X: Features
            y: Labels
            params: Parameters (if None, uses self.best_params)

        Returns:
            Trained model
        """
        if params is None:
            if self.best_params is None:
                raise ValueError("No parameters provided and no optimization run!")
            params = self.best_params.copy()

        # Add required params
        params.update({
            'objective': 'regression',
            'metric': 'rmse',
            'verbosity': -1,
            'boosting_type': 'gbdt'
        })

        logger.info("\nTraining final model with best parameters...")

        train_data = lgb.Dataset(X, label=y)
        model = lgb.train(
            params,
            train_data,
            num_boost_round=1000,
            callbacks=[lgb.log_evaluation(period=100)]
        )

        self.model = model
        logger.info(f"Final model trained ({model.num_trees()} trees)")

        return model

    def evaluate(self, X_test: pd.DataFrame, y_test: pd.Series):
        """Evaluate model performance"""
        if self.model is None:
            raise ValueError("Model not trained!")

        y_pred = self.model.predict(X_test)

        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        direction_correct = ((y_pred > 0) == (y_test > 0)).mean()

        logger.info("\n=== Final Model Evaluation ===")
        logger.info(f"RMSE: {rmse:.6f}")
        logger.info(f"Direction Accuracy: {direction_correct:.2%}")

        return {'RMSE': rmse, 'Direction Accuracy': direction_correct}

    def save_model(self, filename: str = "lightgbm_optuna.pkl"):
        """Save optimized model"""
        if self.model is None:
            raise ValueError("Model not trained!")

        model_path = self.model_dir / filename
        joblib.dump({
            'model': self.model,
            'feature_columns': self.feature_columns,
            'best_params': self.best_params
        }, model_path)

        logger.info(f"\nModel saved to {model_path}")
        return model_path


def main():
    """Main training pipeline with Optuna"""

    logger.info("=" * 60)
    logger.info("ML TRAINING WITH OPTUNA")
    logger.info("=" * 60)

    # Initialize trainer
    trainer = MLTrainerOptuna()

    # Load data
    csv_path = "../data/historical/BTCUSDT_1m_test.csv"
    X, y = trainer.prepare_data(csv_path)

    # Split train/test
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info(f"\n=== Data Split ===")
    logger.info(f"Train: {len(X_train)} samples")
    logger.info(f"Test:  {len(X_test)} samples")

    # Optimize hyperparameters
    n_trials = 20  # Increase to 50-100 for production
    logger.info(f"\nRunning {n_trials} optimization trials...")
    logger.info("(This will take a few minutes...)\n")

    best_params, best_score = trainer.optimize_hyperparameters(
        X_train, y_train,
        n_trials=n_trials,
        cv_splits=3
    )

    # Train final model
    trainer.train_final_model(X_train, y_train, best_params)

    # Evaluate
    metrics = trainer.evaluate(X_test, y_test)

    # Save
    trainer.save_model("btcusdt_15m_optuna.pkl")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("OPTUNA TRAINING COMPLETE!")
    logger.info("=" * 60)
    logger.info(f"\nBest Model:")
    logger.info(f"  Direction Accuracy: {metrics['Direction Accuracy']:.2%}")
    logger.info(f"  RMSE: {metrics['RMSE']:.6f}")


if __name__ == "__main__":
    main()
