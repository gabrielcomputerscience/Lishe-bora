import { PageBanner } from "@/components/PageBanner";
import { ContactForm } from "./ContactForm";

export const metadata = { title: "Contact" };
export default function Contact() {
  return (<>
    <PageBanner slot="page:contact" eyebrow="Contact" title="Contact & feedback"
      sub="Questions, feedback or a grievance? Send us a message. Registered users can also raise a case from their portal and track it." />
    <ContactForm />
  </>);
}
