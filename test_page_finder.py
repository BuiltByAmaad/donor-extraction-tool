from page_finder import find_likely_donor_pages

homepage = "https://theclimatecenter.org"

results = find_likely_donor_pages(homepage)

for result in results:
    print(result["score"], result["url"])
