document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    const submitButton = document.getElementById('submit-button');
    if (submitButton) {
        console.log("Submit button found.");
        submitButton.addEventListener('click', async () => {
            console.log("Submit button clicked.");
            const questionInput = document.getElementById('question-input');
            const resultArea = document.getElementById('result-area');
            const question = questionInput.value;

            if (!question) {
                alert('質問を入力してください。');
                return;
            }

            resultArea.innerHTML = '<p>検索中...</p>';
            console.log("Fetching /api/query...");

            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ question: question }),
                });

                console.log("Response received from /api/query");

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`HTTP error! status: ${response.status}, body: ${errorText}`);
                }

                const data = await response.json();
                // バックエンドからのレスポンス構造に合わせて修正
                // 仮にdataオブジェクト全体を整形して表示
                resultArea.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;

            } catch (error) {
                console.error('Error:', error);
                resultArea.innerHTML = `<p>エラーが発生しました。詳細はコンソールを確認してください。</p><p>${error.message}</p>`;
            }
        });
    } else {
        console.error("Submit button not found.");
    }
});