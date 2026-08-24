"""
This script is used to build the category.txt files given 
"""

import argparse
import wikipediaapi
from multiprocessing import Pool

# parse arguments
parser = argparse.ArgumentParser(description="Get articles from Wikipedia categories")
parser.add_argument("-f", "--filepath", type=str, required=True)
parser.add_argument("-s", "--start-at", type=str, default=None,
                    help="Optional: resume processing from this subcategory name (inclusive)")
args = parser.parse_args()

wiki = wikipediaapi.Wikipedia(
    user_agent="WikiWallStreet/1.0 (contact: luke.robert.warner@gmail.com)",
    language="en",
)

def get_articles_from_subcategory(category_name):
    articles = []
    try:
        category = wiki.page("Category:"+category_name)
        if category.exists():
            for article_title in category.categorymembers:
                articles.append(article_title)
        print(f"Found {len(articles)} articles in {category_name}")
    except:
        print(f"Error with category: {category_name}")
    return(articles)

if __name__ == '__main__':
    with open(args.filepath, "r") as f:
        subcategories = f.read().splitlines()

    if args.start_at is not None:
        if args.start_at not in subcategories:
            raise SystemExit(f"Start-at value '{args.start_at}' not found in {args.filepath}")
        subcategories = subcategories[subcategories.index(args.start_at):]

    with Pool(8) as p:
        articles = p.map(get_articles_from_subcategory, subcategories)

    with open(args.filepath.replace("allowed", "search_lists"), "w") as f:
        for a in articles:
            f.write("\n".join(a) + "\n")
