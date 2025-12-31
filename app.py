import gspread
from flask import Flask, render_template, request, jsonify
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from bertopic import BERTopic

# Google Sheets setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Feedback_Form_Response").sheet1

# Load your pretrained BERTopic model
topic_model = BERTopic.load("bertopic_model1 (1)")

# Topic mapping dictionary
feedback_topics = {
    "Sessions related to AI": [0],
    "Internet, Wi-Fi, and Network Connectivity Issues": [1],
    "Need for More Practical, Advanced, Hands-on, and Extended Sessions": [2, 22, 10, 19, 31, 48, 49],
    "Insufficient Break Time and Need for More Frequent Intervals": [3],
    "Teaching methodology & instructor effectiveness": [4, 40, 25],
    "Overall Positive Feedback": [5, 14, 16, 20, 21, 23, 24, 32, 33, 37, 39, 41, 46, 50, 53],
    "Session Pace and Speed of Delivery": [7, 10, 45],
    "Topic Coverage, Depth, and Time Allocation": [8],
    "Session Duration, Intervals, and Time Allocation": [9, 11, 28, 43, 52],
    "Overall Satisfaction with No Suggestions for Improvement": [11],
    "Need for Conceptual Clarity, Basic Explanations, and Learning Resources": [12, 34],
    "Interest in Continued and Advanced Skill-Based Courses": [13],
    "Classroom Infrastructure and Temperature Comfort": [14, 18],
    "Expectations for Practical Data Analytics and Office-Oriented Tools": [15],
    "Classroom Infrastructure and Projector Visibility Issues": [17],
    "Classroom Thermal Comfort and Air Conditioning Issues": [18],
    "Interaction, Activities and Engagement in Learning": [22, 55, 6],
    "Malayalam": [26],
    "Improvement and Minor Operational Suggestions": [27],
    "Audio Quality and Classroom Environment": [29],
    "Coding Related Queries": [30, 54],
    "Content Delivery and Section Quality": [35],
    "Information and Effectiveness of the session": [36],
    "Nothing, No Suggestion": [38, 44],
    "Study Material": [42, 47],
    "Presentation and slides Quality": [51],
    "Sitting capacity": [56]
}

# Empty comments list
empty_comments = ['nil', 'na', 'null', 'no', 'nop', 'noo']

def map_topic_conditional(row):
    """Map numeric BERTopic ID to the topic name or assign 'Nothing, No Suggestion'."""
    if pd.notna(row['topic']):  # topic exists
        for group, ids in feedback_topics.items():
            if row['topic'] in ids:
                return group
        return "Other"  # topic not in dictionary
    else:  # topic is NaN
        sentence_lower = str(row['REMARKS']).lower()
        if any(word in sentence_lower for word in empty_comments):
            return "Nothing, No Suggestion"
        else:
            return "Other"

def analyze_feedback(selected_date, local_csv_path="data_q11_topic.csv"):
    """
    Fetch feedback for the selected date and perform topic-wise sentiment analysis
    only if the data is fetched from Google Form (today's date). Historical CSV is used as-is.
    """
    selected_date = pd.to_datetime(selected_date).date()
    today = datetime.today().date()
    
    if selected_date == today:
        # Fetch today's Google Form responses
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return {}
        print(df["Question 11"].head(5))
        
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df = df[df['Timestamp'].dt.date == selected_date]

        
        # Assign topics using BERTopic
        if "Question 11" in df.columns:
            remarks = df["Question 11"].astype(str).tolist()
            topics, _ = topic_model.transform(remarks)
            df["topic"] = topics
            
            # Map topic IDs or handle empty feedback
            df["topic_group"] = df.apply(map_topic_conditional, axis=1)
        
        # Perform sentiment analysis ONLY for this fetched data
        def get_sentiment(text):
           # senti model
        
        df["sentiment"] = df["REMARKS"].apply(get_sentiment)
        
        # Create topic-wise summary
        result = {}
        topics = df["topic_group"].unique()
        
        for t in topics:
            df_topic = df[df["topic_group"] == t]
            pos_remarks = df_topic[df_topic["sentiment"] == "positive"]["REMARKS"]
            neg_remarks = df_topic[df_topic["sentiment"] == "negative"]["REMARKS"]
            
            result[t] = {
                "positive_remark": pos_remarks.iloc[0] if not pos_remarks.empty else "",
                "negative_remark": neg_remarks.iloc[0] if not neg_remarks.empty else "",
                "pos_count": len(pos_remarks),
                "neg_count": len(neg_remarks)
            }
        
        return result
    
    else:
        # Load historical processed data
        df = pd.read_csv(local_csv_path)

        df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])
        df = df[df['TIMESTAMP'].dt.date == selected_date]

        if df.empty:
            return {}

        # Ensure required columns exist
        required_cols = {"topic_group", "sentiment"}
        if not required_cols.issubset(df.columns):
            return {"error": "Required columns missing in historical dataset"}

        # Topic-wise sentiment aggregation
        summary = (
            df.groupby(["topic_group", "sentiment"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )

        # Convert to frontend-friendly format
        result = {}
        for _, row in summary.iterrows():
            result[row["topic_group"]] = {
                "positive": int(row.get("positive", 0)),
                "neutral": int(row.get("neutral", 0)),
                "negative": int(row.get("negative", 0)),
                "overall_score": int(row.get("positive", 0)) - int(row.get("negative", 0))
            }

        return result
  # return as-is, with topic_group already present

def overall_sentiment_by_topic(df):
    """
    Computes overall sentiment score per topic using sentence-level sentiment scores
    """

    if df.empty:
        return {}

    result = {}

    grouped = df.groupby("topic_group")

    for topic, group in grouped:
        scores = group["sentiment_score"]

        mean_score = scores.mean()

        pos_count = (scores > 0).sum()
        neg_count = (scores < 0).sum()
        neu_count = (scores == 0).sum()

        # Assign final label
        if mean_score > 0.05:
            label = "Positive"
        elif mean_score < -0.05:
            label = "Negative"
        else:
            label = "Neutral"

        result[topic] = {
            "overall_score": round(mean_score, 3),
            "label": label,
            "positive_count": int(pos_count),
            "negative_count": int(neg_count),
            "neutral_count": int(neu_count),
            "total_sentences": len(scores)
        }

    return result
app = Flask(__name__)  
# Example usage
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/form-sentiments/")
def form_sentiment():
    return render_template("Form.html")

@app.route("/overall-sentiments/")
def overall_sentiment():
    return render_template("Overall.html")



@app.route("/analyze", methods=["POST"])
def analyze():
    session_name = request.form.get("COURSE_ID")
    session_date = request.form.get("DATE")

    df_filtered = analyze_feedback(session_date, session_name)

    if df_filtered.empty:
        return jsonify({"error": "No data found"})

    # Filter by session_name if exists
    if session_name and "session_name" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["session_name"] == session_name]
    
    if df_filtered.empty:
        return jsonify({"error": "No data found for this session"})

    grouped = (
        df_filtered
        .groupby(["topic_group", "sentiment"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    response = {
        "topics": grouped["topic_group"].tolist(),
        "positive": grouped.get("positive", []).tolist(),
        "neutral": grouped.get("neutral", []).tolist(),
        "negative": grouped.get("negative", []).tolist()
    }

    return jsonify(response)

if __name__ == "__main__":
    app.run(debug=True)
