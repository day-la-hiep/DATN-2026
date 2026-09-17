from tool.cnn_predictor import SkinCNNPredictor


CHECKPOINT = "model_output/AdaptiveCNN_SkinDisease_v5_best.pth"
IMAGE = "test_imgs/image.png"


def main():

    # Load model
    predictor = SkinCNNPredictor(
        checkpoint_path=CHECKPOINT
    )

    # Top-1
    result = predictor.predict_top1(IMAGE)

    print("\n" + "=" * 80)
    print("TOP-1 PREDICTION")
    print("=" * 80)

    print("Disease     :", result["disease"])
    print("Class ID    :", result["class_id"])
    print("Confidence  :", f"{result['confidence'] * 100:.2f}%")

    # Top-5
    results = predictor.predict(
        IMAGE,
        top_k=5
    )

    print("\n" + "=" * 80)
    print("TOP-5 PREDICTIONS")
    print("=" * 80)

    for result in results:

        print(
            f"{result['rank']}. "
            f"{result['disease']:<30} "
            f"{result['confidence_percent']:.2f}%"
        )


if __name__ == "__main__":
    main()