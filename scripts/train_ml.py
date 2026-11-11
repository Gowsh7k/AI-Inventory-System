
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import (
    silhouette_score,
    davies_bouldin_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score
)
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.cluster import KMeans
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split

import numpy as np
import sqlite3
import pandas as pd
import joblib
import os

os.makedirs('models', exist_ok=True)
os.makedirs('models/experiments', exist_ok=True)
os.makedirs('ml_training/outputs', exist_ok=True)

DB_FILE = 'data/inventory.db'


def fetch_data():
    conn = sqlite3.connect(DB_FILE)

    items_query = """
        SELECT i.id, i.price, i.stock_quantity, i.reorder_level,
               COALESCE(SUM(s.quantity_sold), 0) as total_sales_vol
        FROM inventory i
        LEFT JOIN sales_history s ON i.id = s.item_id
        GROUP BY i.id
    """

    items_df = pd.read_sql_query(items_query, conn)

    sales_query = """
        SELECT item_id,
               strftime('%Y-%m', sale_date) as month,
               SUM(quantity_sold) as monthly_qty
        FROM sales_history
        GROUP BY item_id, month
        ORDER BY item_id, month
    """

    sales_df = pd.read_sql_query(sales_query, conn)
    conn.close()

    return items_df, sales_df


def train_segmentation(items_df):
    print("\nTraining K-Means Segmentation Model...")

    X = items_df[
        ['price', 'stock_quantity', 'total_sales_vol']
    ]

    if len(X) < 4:
        print("Not enough product records for training.")
        return

    X_train, X_test = train_test_split(
        X,
        test_size=0.2,
        random_state=42
    )

    model = Pipeline([
        ('scaler', StandardScaler()),
        ('kmeans', KMeans(
            n_clusters=3,
            random_state=42,
            n_init=10
        ))
    ])

    model.fit(X_train)

    train_clusters = model.predict(X_train)
    test_clusters = model.predict(X_test)

    X_test_scaled = model.named_steps['scaler'].transform(X_test)

    if (
        len(set(test_clusters)) > 1
        and len(set(test_clusters)) < len(test_clusters)
    ):
        print(
            "Silhouette Score:",
            silhouette_score(X_test_scaled, test_clusters)
        )
        print(
            "Davies-Bouldin Score:",
            davies_bouldin_score(X_test_scaled, test_clusters)
        )
    else:
        print("Not enough different clusters for evaluation.")

    print(
        "K-Means Inertia:",
        model.named_steps['kmeans'].inertia_
    )

    cluster_results = X_test.copy()
    cluster_results['cluster'] = test_clusters

    cluster_results.to_csv(
        'ml_training/outputs/kmeans_test_clusters.csv',
        index=False
    )

    joblib.dump(model, 'models/segment_model.pkl')

    print("Training records:", len(X_train))
    print("Testing records:", len(X_test))
    print("Training clusters:", train_clusters)
    print("Testing clusters:", test_clusters)
    print("Cluster results saved successfully.")
    print("Segmentation model saved successfully.")


def train_demand_prediction(sales_df):
    print("\nTraining Demand Prediction Models...")

    if sales_df.empty:
        print("No sales data available.")
        return

    sales_df = sales_df.dropna(
        subset=['item_id', 'month', 'monthly_qty']
    )

    pivot_df = sales_df.pivot(
        index='item_id',
        columns='month',
        values='monthly_qty'
    ).fillna(0)

    pivot_df = pivot_df.sort_index(axis=1)

    records = []

    for item_id in pivot_df.index:

        monthly_sales = pivot_df.loc[item_id].values
        months = pivot_df.columns.tolist()

        for i in range(3, len(monthly_sales)):

            previous_sales = monthly_sales[i-3:i]
            target_month = months[i]

            month_number = int(target_month.split('-')[1])

            records.append({
                'item_id': str(item_id),
                'lag_1': monthly_sales[i-1],
                'lag_2': monthly_sales[i-2],
                'lag_3': monthly_sales[i-3],
                'rolling_mean_3': np.mean(previous_sales),
                'rolling_std_3': np.std(previous_sales),
                'month_sin': np.sin(
                    2 * np.pi * month_number / 12
                ),
                'month_cos': np.cos(
                    2 * np.pi * month_number / 12
                ),
                'target_month': target_month,
                'actual': monthly_sales[i]
            })

    if len(records) < 10:
        print("Not enough records for model comparison.")
        return

    data = pd.DataFrame(records).sort_values(
        'target_month'
    )

    unique_months = sorted(data['target_month'].unique())

    if len(unique_months) < 2:
        print("Not enough different months for chronological splitting.")
        return

    # Chronological 80/20 split
    split_index = int(len(unique_months) * 0.8)
    split_index = max(
        1,
        min(split_index, len(unique_months) - 1)
    )

    cutoff_month = unique_months[split_index]

    train_data = data[
        data['target_month'] < cutoff_month
    ].copy()

    test_data = data[
        data['target_month'] >= cutoff_month
    ].copy()

    if train_data.empty or test_data.empty:
        print("Insufficient training or testing records.")
        return

    numeric_features = [
        'lag_1',
        'lag_2',
        'lag_3',
        'rolling_mean_3',
        'rolling_std_3',
        'month_sin',
        'month_cos'
    ]

    categorical_features = ['item_id']

    feature_columns = numeric_features + categorical_features

    X_train = train_data[feature_columns]
    y_train = train_data['actual']

    X_test = test_data[feature_columns]
    y_test = test_data['actual']

    def create_preprocessor():
        return ColumnTransformer([
            (
                'numeric',
                StandardScaler(),
                numeric_features
            ),
            (
                'product',
                OneHotEncoder(handle_unknown='ignore'),
                categorical_features
            )
        ])

    models = {
        'Linear Regression': LinearRegression(),

        'Ridge Regression': Ridge(
            alpha=1.0
        ),

        'Random Forest': RandomForestRegressor(
            n_estimators=200,
            max_depth=10,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
    }

    results = []
    predictions_by_model = {}
    trained_models = {}

    print("\nMODEL COMPARISON")

    for name, regressor in models.items():

        pipeline = Pipeline([
            ('preprocessor', create_preprocessor()),
            ('regressor', regressor)
        ])

        pipeline.fit(X_train, y_train)

        predictions = pipeline.predict(X_test)

        mae = mean_absolute_error(
            y_test,
            predictions
        )

        mse = mean_squared_error(
            y_test,
            predictions
        )

        rmse = np.sqrt(mse)

        r2 = r2_score(
            y_test,
            predictions
        ) if len(y_test) >= 2 else np.nan

        results.append({
            'Model': name,
            'MAE': mae,
            'MSE': mse,
            'RMSE': rmse,
            'R2': r2
        })

        predictions_by_model[name] = predictions
        trained_models[name] = pipeline

        print(f"\n{name}")
        print("MAE:", mae)
        print("MSE:", mse)
        print("RMSE:", rmse)
        print("R2:", r2)

    # Previous month sales baseline
    baseline_predictions = test_data[
        'lag_1'
    ].to_numpy()

    baseline_mae = mean_absolute_error(
        y_test,
        baseline_predictions
    )

    baseline_mse = mean_squared_error(
        y_test,
        baseline_predictions
    )

    baseline_rmse = np.sqrt(baseline_mse)

    baseline_r2 = (
        r2_score(y_test, baseline_predictions)
        if len(y_test) >= 2 else np.nan
    )

    results.append({
        'Model': 'Previous Month Baseline',
        'MAE': baseline_mae,
        'MSE': baseline_mse,
        'RMSE': baseline_rmse,
        'R2': baseline_r2
    })

    comparison = pd.DataFrame(results)

    comparison = comparison.sort_values(
        'RMSE'
    )

    print("\nFINAL MODEL COMPARISON")
    print(comparison.to_string(index=False))

    # Save comparison results
    comparison.to_csv(
        'ml_training/outputs/model_comparison.csv',
        index=False
    )

    # Save experimental models separately
    for name, pipeline in trained_models.items():

        filename = name.lower().replace(' ', '_')

        joblib.dump(
            pipeline,
            f'models/experiments/{filename}.pkl'
        )

    # Save improved Linear Regression separately
    joblib.dump(
        trained_models['Linear Regression'],
        'models/demand_model_improved.pkl'
    )

    # Save predictions from every model
    demand_results = pd.DataFrame({
        'item_id': test_data['item_id'].values,
        'target_month': test_data['target_month'].values,
        'actual': y_test.to_numpy(),
        'baseline_prediction': baseline_predictions,
        'linear_regression': predictions_by_model['Linear Regression'],
        'ridge_regression': predictions_by_model['Ridge Regression'],
        'random_forest': predictions_by_model['Random Forest']
    })

    demand_results.to_csv(
        'ml_training/outputs/demand_predictions.csv',
        index=False
    )

    print("\nTraining records:", len(X_train))
    print("Testing records:", len(X_test))
    print(
        "Testing months:",
        sorted(test_data['target_month'].unique())
    )

    best_model = comparison[
        comparison['Model'] != 'Previous Month Baseline'
    ].sort_values('RMSE').iloc[0]

    print("\nBest experimental model by RMSE:", best_model['Model'])
    print("Best RMSE:", best_model['RMSE'])

    print("\nAll experimental models saved successfully.")
    print("Model comparison CSV saved successfully.")
    print("Demand predictions CSV saved successfully.")


def main():
    items_df, sales_df = fetch_data()

    train_segmentation(items_df)
    train_demand_prediction(sales_df)

    print("\nML Training Complete!")


if __name__ == "__main__":
    main()

