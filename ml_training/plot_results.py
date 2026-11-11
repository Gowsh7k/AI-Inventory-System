import os
import pandas as pd
import matplotlib.pyplot as plt

output_dir = os.path.join("ml_training", "outputs")
os.makedirs(output_dir, exist_ok=True)

comparison_file = f'{output_dir}/model_comparison.csv'
demand_file = f'{output_dir}/demand_predictions.csv'
cluster_file = f'{output_dir}/kmeans_test_clusters.csv'

if not os.path.exists(comparison_file):
    print("Run train_ml.py first.")
    exit()

comparison = pd.read_csv(comparison_file)

# Model performance comparison
plt.figure(figsize=(9, 5))
plt.bar(comparison['Model'], comparison['RMSE'])
plt.xlabel('Machine Learning Model')
plt.ylabel('RMSE')
plt.title('Demand Prediction Model Comparison')
plt.xticks(rotation=15)
plt.tight_layout()
plt.savefig(f'{output_dir}/model_comparison.png')
plt.close()

if os.path.exists(demand_file):

    demand = pd.read_csv(demand_file)

    model_columns = {
        'Linear Regression': 'linear_regression',
        'Ridge Regression': 'ridge_regression',
        'Random Forest': 'random_forest'
    }

    # Actual versus predicted comparison
    plt.figure(figsize=(8, 6))

    for name, column in model_columns.items():
        plt.scatter(
            demand['actual'],
            demand[column],
            label=name,
            alpha=0.6
        )

    minimum = min(
        demand['actual'].min(),
        demand[list(model_columns.values())].min().min()
    )

    maximum = max(
        demand['actual'].max(),
        demand[list(model_columns.values())].max().max()
    )

    plt.plot(
        [minimum, maximum],
        [minimum, maximum],
        linestyle='--',
        label='Perfect Prediction'
    )

    plt.xlabel('Actual Sales')
    plt.ylabel('Predicted Sales')
    plt.title('Actual vs Predicted Demand - Model Comparison')
    plt.legend()
    plt.tight_layout()
    plt.savefig(f'{output_dir}/actual_vs_predicted.png')
    plt.close()

    # Residual comparison for each model
    plt.figure(figsize=(8, 5))

    for name, column in model_columns.items():
        residuals = demand['actual'] - demand[column]

        plt.scatter(
            demand[column],
            residuals,
            label=name,
            alpha=0.6
        )

    plt.axhline(y=0, linestyle='--')
    plt.xlabel('Predicted Sales')
    plt.ylabel('Prediction Error')
    plt.title('Residual Comparison')
    plt.legend()
    plt.tight_layout()
    plt.savefig(f'{output_dir}/residual_plot.png')
    plt.close()

if os.path.exists(cluster_file):

    clusters = pd.read_csv(cluster_file)

    plt.figure(figsize=(8, 5))

    plt.scatter(
        clusters['price'],
        clusters['stock_quantity'],
        c=clusters['cluster'],
        cmap='viridis'
    )

    plt.xlabel('Product Price')
    plt.ylabel('Stock Quantity')
    plt.title('K-Means Inventory Segmentation')
    plt.colorbar(label='Cluster')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "kmeans_clusters.png"), dpi=300, bbox_inches="tight")
    plt.close()
    plt.close()

print("\nAll evaluation graphs generated successfully!")
print("Graphs saved in:", output_dir)
