# 🐾 Bosbos Cat Finder

> Automated twice-daily scraper & interactive Firebase dashboard designed to find **Bosbos** — a female kitten ($\le 20\text{ weeks}$, the younger the better) with bright/white colors and cute features across Calgary's top online adoption centers and rescues.

---

## 🌟 Key Features

1. **Multi-Source Calgary Scraper**:
   - **MEOW Foundation**: Calgary's leading cat-only rescue (extracts ages in weeks, bios, personality, photos).
   - **Calgary Humane Society**: Calgary's primary full-service shelter (Petango live cards).
   - **Cochrane & Area Humane Society**: Dynamic CMS collection for Calgary West commuter area.
   - Expandable architecture for additional shelters.
2. **Bosbos Intelligence & Ranking Engine**:
   - **Strict Filtering**: Female ONLY, $\le 20\text{ weeks}$ (kittens).
   - **Youth Weighting (40 pts)**: Prioritizes younger kittens ($\le 8\text{ wks} > 12\text{ wks} > 16\text{ wks}$).
   - **Bright/White Palette Scoring (40 pts)**: Pure white, cream, flame point, lynx point, lilac point, peach/buff, champagne, pastel calico.
   - **Cute Personality & Facial Analysis (20 pts)**: Identifies affectionate traits like cuddle, sweet, tiny, purr, big eyes, lap kitten.
3. **Friend Voting & Like System**:
   - Shareable link so friends can browse and upvote their favorite kittens.
   - Sort by **Most Liked by Friends**, **Bosbos Match Score**, **Youngest First**, or **Newest**.
   - Filter by **Liked Only**, **My Favorites**, **New Today**, or **White/Cream Palette**.
   - Dual-mode support: Seamless local storage voting out of the box, with instant real-time sync across devices when connected to Firebase Realtime Database.
4. **Automated Twice-Daily Runner**:
   - GitHub Actions workflow runs every day at **8:00 AM** and **5:00 PM** Calgary time (00:00 and 15:00 UTC).
   - Automatically commits fresh candidates and deploys to Firebase Hosting.

---

## 🚀 Quick Start (Local Run)

```bash
# 1. Clone repository
git clone https://github.com/Nahossai/bosbos-cat-finder.git
cd bosbos-cat-finder

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run scraper
python scrape_and_update.py

# 4. Preview local dashboard
cd public && python -m http.server 8080
# Open http://localhost:8080 in your browser
```

---

## 🔥 Deploying to Firebase Hosting

### Step 1: Set your Firebase Project ID
Open `.firebaserc` and replace `YOUR_FIREBASE_PROJECT_ID` with your Firebase project ID:
```json
{
  "projects": {
    "default": "your-firebase-project-id"
  }
}
```

### Step 2: (Optional) Connect Firebase Realtime Database for Live Friend Syncing
Open `public/firebase-config.js` and paste your Firebase Web App credentials:
```javascript
window.FIREBASE_CONFIG = {
  apiKey: "AIzaSy...",
  authDomain: "your-project.firebaseapp.com",
  databaseURL: "https://your-project-default-rtdb.firebaseio.com",
  projectId: "your-project-id",
  storageBucket: "your-project.appspot.com",
  appId: "1:..."
};
```
*(If left empty, friend likes are stored in local browser storage.)*

### Step 3: Deploy via CLI
```bash
npm install -g firebase-tools
firebase login
firebase deploy --only hosting
```

### Step 4: Enable Automated Deployments via GitHub Actions
To let GitHub Actions deploy to Firebase automatically every day:
1. Generate a Firebase service account key in the Firebase Console (`Project Settings -> Service Accounts -> Generate new private key`).
2. In your GitHub repository, navigate to **Settings -> Secrets and variables -> Actions**.
3. Add two secrets:
   - `FIREBASE_SERVICE_ACCOUNT`: The JSON content of your service account key.
   - `FIREBASE_PROJECT_ID`: Your Firebase project ID.
4. The workflow will now automatically scrape and deploy twice every single day!

---

## 🏛️ Calgary Online Cat Adoption Directory

| Organization | Website | Focus / Specialty |
| :--- | :--- | :--- |
| **MEOW Foundation** | [meowfoundation.com](https://meowfoundation.com/adoptable-cats/) | Calgary's premier cat-only rescue; operates Adoption Centre & Regal Cat Café. |
| **Calgary Humane Society** | [calgaryhumane.ca](https://www.calgaryhumane.ca/adopt/cats/) | Full-service shelter with open adoption and same-day matching. |
| **City of Calgary Animal Services** | [calgary.ca/pets](https://www.calgary.ca/pets/adoption.html) | Municipal shelter listings on 24PetConnect. |
| **Cochrane & Area Humane Society** | [cochranehumane.ca](https://www.cochranehumane.ca/adopt) | High intake of kittens and litters, West Calgary area. |
| **AARCS (Alberta Animal Rescue Crew)** | [aarcs.ca](https://aarcs.ca/adoptable-cats/) | Safe Haven facility in SE Calgary + vast foster home network. |
| **Pawsitive Match Rescue** | [pawsitivematch.org](https://www.pawsitivematch.org/) | Foster-based dog and cat rescue in Calgary. |
| **Animal Rescue Foundation (ARF)** | [arf.ab.ca](https://arf.ab.ca/) | Stray rescue and foster network across Alberta. |
| **Petfinder (Calgary Region)** | [petfinder.com](https://www.petfinder.com/search/cats-for-adoption/ca/ab/calgary/) | Multi-shelter aggregator indexing 15+ Calgary rescues. |

---

## 🧪 Testing

```bash
python -m unittest discover tests
```
